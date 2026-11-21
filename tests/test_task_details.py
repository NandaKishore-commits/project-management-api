import pytest

from tests.helpers import API, days_from_today, project_payload, task_payload


def make_task(client, headers, project_id, **overrides):
    r = client.post(f"{API}/tasks", json=task_payload(project_id, **overrides), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def add_dependency(client, headers, task_id, depends_on_id):
    return client.post(
        f"{API}/tasks/{task_id}/dependencies",
        json={"depends_on_id": depends_on_id},
        headers=headers,
    )


def checklist_url(task, suffix=""):
    return f"{API}/tasks/{task['id']}/checklists{suffix}"


# ---------- new task fields ----------

def test_task_has_start_date_and_estimated_hours(client, manager, project):
    body = make_task(
        client, manager["headers"], project["id"],
        start_date=days_from_today(1), estimated_hours=6.5,
    )
    assert body["start_date"] == days_from_today(1)
    assert body["estimated_hours"] == 6.5


@pytest.mark.parametrize(
    "override",
    [
        {"start_date": days_from_today(20), "deadline": days_from_today(10)},
        {"estimated_hours": 0},
        {"estimated_hours": -2},
    ],
)
def test_invalid_start_date_or_hours(client, manager, project, override):
    r = client.post(
        f"{API}/tasks", json=task_payload(project["id"], **override), headers=manager["headers"]
    )
    assert r.status_code == 422


def test_update_compares_start_date_with_the_saved_deadline(client, manager, task):
    # the task deadline is 10 days from now
    r = client.put(
        f"{API}/tasks/{task['id']}", json={"start_date": days_from_today(30)}, headers=manager["headers"]
    )
    assert r.status_code == 400


# ---------- subtasks ----------

def test_create_and_list_subtasks(client, manager, member, task):
    sub = make_task(client, manager["headers"], task["project_id"], title="Sub one", parent_task_id=task["id"])
    assert sub["parent_task_id"] == task["id"]
    r = client.get(f"{API}/tasks/{task['id']}/subtasks", headers=member["headers"])
    assert r.status_code == 200
    assert [t["title"] for t in r.json()] == ["Sub one"]


def test_subtask_rules(client, manager, project, task):
    h = manager["headers"]
    other = client.post(f"{API}/projects", json=project_payload(name="Other project"), headers=h).json()

    r = client.post(
        f"{API}/tasks", json=task_payload(other["id"], title="Wrong project", parent_task_id=task["id"]), headers=h
    )
    assert r.status_code == 400

    r = client.post(
        f"{API}/tasks", json=task_payload(project["id"], title="Ghost parent", parent_task_id=9999), headers=h
    )
    assert r.status_code == 404

    sub = make_task(client, h, project["id"], title="Level one", parent_task_id=task["id"])
    r = client.post(
        f"{API}/tasks", json=task_payload(project["id"], title="Level two", parent_task_id=sub["id"]), headers=h
    )
    assert r.status_code == 400  # a subtask cannot have subtasks


def test_parent_cannot_complete_before_its_subtasks(client, manager, task):
    h = manager["headers"]
    sub = make_task(client, h, task["project_id"], title="Open subtask", parent_task_id=task["id"])
    url = f"{API}/tasks/{task['id']}/status"

    r = client.patch(url, json={"status": "COMPLETED"}, headers=h)
    assert r.status_code == 400
    assert "Open subtask" in r.json()["detail"]

    client.patch(f"{API}/tasks/{sub['id']}/status", json={"status": "COMPLETED"}, headers=h)
    assert client.patch(url, json={"status": "COMPLETED"}, headers=h).status_code == 200


# ---------- dependencies ----------

@pytest.fixture()
def two_tasks(client, manager, project):
    a = make_task(client, manager["headers"], project["id"], title="Task A")
    b = make_task(client, manager["headers"], project["id"], title="Task B")
    return a, b


def test_dependency_blocks_the_task_until_the_prerequisite_is_completed(client, manager, two_tasks):
    a, b = two_tasks
    h = manager["headers"]

    r = add_dependency(client, h, b["id"], a["id"])
    assert r.status_code == 201, r.text
    assert r.json()["is_blocked"] is True
    assert [t["title"] for t in r.json()["depends_on"]] == ["Task A"]

    status_url = f"{API}/tasks/{b['id']}/status"
    r = client.patch(status_url, json={"status": "IN_PROGRESS"}, headers=h)
    assert r.status_code == 400
    assert "Task A" in r.json()["detail"]

    client.patch(f"{API}/tasks/{a['id']}/status", json={"status": "COMPLETED"}, headers=h)
    assert client.get(f"{API}/tasks/{b['id']}/dependencies", headers=h).json()["is_blocked"] is False
    assert client.patch(status_url, json={"status": "IN_PROGRESS"}, headers=h).status_code == 200


def test_dependency_rules(client, manager, two_tasks):
    a, b = two_tasks
    h = manager["headers"]
    assert add_dependency(client, h, a["id"], a["id"]).status_code == 400  # itself
    assert add_dependency(client, h, a["id"], 9999).status_code == 404
    assert add_dependency(client, h, b["id"], a["id"]).status_code == 201
    assert add_dependency(client, h, b["id"], a["id"]).status_code == 409  # duplicate

    r = add_dependency(client, h, a["id"], b["id"])  # A needs B, B needs A
    assert r.status_code == 400
    assert "circular" in r.json()["detail"]


def test_longer_loops_are_blocked_too(client, manager, project):
    h = manager["headers"]
    ids = [make_task(client, h, project["id"], title=f"Chain {n}")["id"] for n in range(3)]
    assert add_dependency(client, h, ids[1], ids[0]).status_code == 201
    assert add_dependency(client, h, ids[2], ids[1]).status_code == 201
    assert add_dependency(client, h, ids[0], ids[2]).status_code == 400


def test_dependency_across_projects_is_rejected(client, manager, task):
    h = manager["headers"]
    other = client.post(f"{API}/projects", json=project_payload(name="Other project"), headers=h).json()
    foreign = make_task(client, h, other["id"], title="Foreign task")
    assert add_dependency(client, h, task["id"], foreign["id"]).status_code == 400


def test_remove_dependency(client, manager, two_tasks):
    a, b = two_tasks
    h = manager["headers"]
    add_dependency(client, h, b["id"], a["id"])
    url = f"{API}/tasks/{b['id']}/dependencies/{a['id']}"
    assert client.delete(url, headers=h).status_code == 204
    assert client.get(f"{API}/tasks/{b['id']}/dependencies", headers=h).json()["depends_on"] == []
    assert client.delete(url, headers=h).status_code == 404


def test_only_managers_change_dependencies(client, member, two_tasks):
    a, b = two_tasks
    assert add_dependency(client, member["headers"], b["id"], a["id"]).status_code == 403


def test_a_deleted_prerequisite_does_not_block(client, manager, two_tasks):
    a, b = two_tasks
    h = manager["headers"]
    add_dependency(client, h, b["id"], a["id"])
    client.delete(f"{API}/tasks/{a['id']}", headers=h)
    r = client.patch(f"{API}/tasks/{b['id']}/status", json={"status": "IN_PROGRESS"}, headers=h)
    assert r.status_code == 200


# ---------- checklists ----------

def test_checklist_progress(client, manager, member, task):
    r = client.post(checklist_url(task), json={"title": "Release"}, headers=member["headers"])
    assert r.status_code == 201, r.text  # the member is the assignee
    cid = r.json()["id"]
    assert r.json()["progress_percent"] == 0.0

    for text in ("Write code", "Run tests"):
        r = client.post(checklist_url(task, f"/{cid}/items"), json={"content": text}, headers=member["headers"])
        assert r.status_code == 201, r.text
    item_id = r.json()["items"][0]["id"]

    r = client.patch(
        checklist_url(task, f"/{cid}/items/{item_id}"), json={"is_done": True}, headers=member["headers"]
    )
    assert r.status_code == 200
    assert r.json()["progress_percent"] == 50.0

    listed = client.get(checklist_url(task), headers=manager["headers"]).json()
    assert listed[0]["title"] == "Release"
    assert [i["is_done"] for i in listed[0]["items"]] == [True, False]


def test_checklist_permissions(client, manager, make_user, outsider, project, task):
    other = make_user("other@test.com")
    client.post(
        f"{API}/projects/{project['id']}/members", json={"user_id": other["id"]}, headers=manager["headers"]
    )
    # a project member who is not the assignee can read, but not change
    assert client.post(checklist_url(task), json={"title": "Nope"}, headers=other["headers"]).status_code == 403
    assert client.get(checklist_url(task), headers=other["headers"]).status_code == 200
    assert client.get(checklist_url(task), headers=outsider["headers"]).status_code == 403


def test_checklist_validation_and_404(client, manager, task):
    h = manager["headers"]
    assert client.post(checklist_url(task), json={"title": "   "}, headers=h).status_code == 422
    assert client.post(checklist_url(task, "/9999/items"), json={"content": "x"}, headers=h).status_code == 404
    cid = client.post(checklist_url(task), json={"title": "List"}, headers=h).json()["id"]
    assert client.post(checklist_url(task, f"/{cid}/items"), json={"content": ""}, headers=h).status_code == 422


def test_delete_checklist_and_item(client, manager, task):
    h = manager["headers"]
    cid = client.post(checklist_url(task), json={"title": "List"}, headers=h).json()["id"]
    item_id = client.post(
        checklist_url(task, f"/{cid}/items"), json={"content": "Step"}, headers=h
    ).json()["items"][0]["id"]
    assert client.delete(checklist_url(task, f"/{cid}/items/{item_id}"), headers=h).status_code == 204
    assert client.delete(checklist_url(task, f"/{cid}"), headers=h).status_code == 204
    assert client.get(checklist_url(task), headers=h).json() == []


# ---------- watchers ----------

def test_watchers(client, manager, member, outsider, task):
    url = f"{API}/tasks/{task['id']}/watchers"

    r = client.post(url, json={"user_id": member["id"]}, headers=member["headers"])
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == member["email"]
    assert client.post(url, json={"user_id": member["id"]}, headers=member["headers"]).status_code == 409
    # a member cannot add someone else
    assert client.post(url, json={"user_id": manager["id"]}, headers=member["headers"]).status_code == 403
    # a manager can, but only a project member
    assert client.post(url, json={"user_id": outsider["id"]}, headers=manager["headers"]).status_code == 400

    assert len(client.get(url, headers=manager["headers"]).json()) == 1
    assert client.delete(f"{url}/{member['id']}", headers=member["headers"]).status_code == 204
    assert client.get(url, headers=manager["headers"]).json() == []


# ---------- history ----------

def test_history_records_old_and_new_values(client, manager, member, task):
    h = manager["headers"]
    client.put(f"{API}/tasks/{task['id']}", json={"title": "Renamed task"}, headers=h)
    client.patch(f"{API}/tasks/{task['id']}/priority", json={"priority": "CRITICAL"}, headers=h)
    client.patch(
        f"{API}/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}, headers=member["headers"]
    )

    r = client.get(f"{API}/tasks/{task['id']}/history", headers=h)
    assert r.status_code == 200
    rows = {(i["field"], i["old_value"], i["new_value"], i["user"]["email"]) for i in r.json()["items"]}
    assert ("title", "Design homepage", "Renamed task", manager["email"]) in rows
    assert ("priority", "HIGH", "CRITICAL", manager["email"]) in rows
    assert ("status", "TODO", "IN_PROGRESS", member["email"]) in rows


def test_reassignment_is_recorded_in_the_history(client, make_user, manager, project, task):
    other = make_user("other@test.com")
    client.post(
        f"{API}/projects/{project['id']}/members", json={"user_id": other["id"]}, headers=manager["headers"]
    )
    r = client.patch(
        f"{API}/tasks/{task['id']}/assign",
        json={"assigned_to": other["id"], "reason": "More capacity"},
        headers=manager["headers"],
    )
    assert r.status_code == 200, r.text
    items = client.get(f"{API}/tasks/{task['id']}/history", headers=manager["headers"]).json()["items"]
    assert any(
        i["field"] == "assigned_to" and i["old_value"] == "Member" and i["new_value"] == "Other"
        for i in items
    )


def test_history_is_private_to_project_members(client, outsider, task):
    assert client.get(f"{API}/tasks/{task['id']}/history", headers=outsider["headers"]).status_code == 403