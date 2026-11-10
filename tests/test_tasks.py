import pytest

from app.utils.enums import RoleName
from tests.helpers import API, days_from_today, task_payload


@pytest.fixture()
def four_tasks(client, manager, member, project):
    """Four tasks with different priorities and deadlines (the last one has no deadline)."""
    specs = [
        {"title": "Fix login bug", "priority": "CRITICAL", "deadline": days_from_today(5), "assigned_to": member["id"]},
        {"title": "Design homepage", "priority": "HIGH", "deadline": days_from_today(10), "assigned_to": member["id"]},
        {"title": "Write content", "priority": "MEDIUM", "deadline": days_from_today(20)},
        {"title": "Setup hosting", "priority": "LOW", "deadline": None},
    ]
    created = {}
    for spec in specs:
        r = client.post(f"{API}/tasks", json=task_payload(project["id"], **spec), headers=manager["headers"])
        assert r.status_code == 201, r.text
        created[spec["title"]] = r.json()
    return created


def list_titles(client, headers, **params):
    r = client.get(f"{API}/tasks", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return [t["title"] for t in r.json()["items"]]


# ---------- create ----------

def test_manager_creates_a_task(client, manager, project):
    r = client.post(f"{API}/tasks", json=task_payload(project["id"]), headers=manager["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "TODO"
    assert body["created_by"] == manager["id"]
    assert body["updated_by"] == manager["id"]
    assert body["assigned_to"] is None


def test_a_new_task_always_starts_as_todo(client, manager, project):
    r = client.post(f"{API}/tasks", json=task_payload(project["id"], status="COMPLETED"), headers=manager["headers"])
    assert r.status_code == 201
    assert r.json()["status"] == "TODO"


@pytest.mark.parametrize(
    "override, expected",
    [
        ({"title": "ab"}, 422),                          # title too short
        ({"priority": "URGENT"}, 422),                   # not a real priority
        ({"deadline": days_from_today(-1)}, 422),        # deadline in the past
        ({"deadline": days_from_today(120)}, 400),       # after the project end (90 days)
        ({"assigned_to": 9999}, 400),                    # user does not exist
    ],
)
def test_task_creation_rules(client, manager, project, override, expected):
    r = client.post(f"{API}/tasks", json=task_payload(project["id"], **override), headers=manager["headers"])
    assert r.status_code == expected, r.text


def test_task_in_a_missing_project(client, manager, project):
    r = client.post(f"{API}/tasks", json=task_payload(9999), headers=manager["headers"])
    assert r.status_code == 404


def test_task_can_only_be_assigned_to_project_members(client, manager, outsider, project):
    r = client.post(f"{API}/tasks", json=task_payload(project["id"], assigned_to=outsider["id"]), headers=manager["headers"])
    assert r.status_code == 400
    assert "member" in r.json()["detail"]


def test_task_cannot_be_assigned_to_a_deactivated_member(client, admin, manager, member, project):
    client.patch(f"{API}/users/{member['id']}/status", json={"is_active": False}, headers=admin["headers"])
    r = client.post(f"{API}/tasks", json=task_payload(project["id"], assigned_to=member["id"]), headers=manager["headers"])
    assert r.status_code == 400


def test_team_member_cannot_create_a_task(client, member, project):
    r = client.post(f"{API}/tasks", json=task_payload(project["id"]), headers=member["headers"])
    assert r.status_code == 403


def test_manager_of_another_project_cannot_create_a_task(client, make_user, project):
    other = make_user("manager2@test.com", RoleName.PROJECT_MANAGER)
    r = client.post(f"{API}/tasks", json=task_payload(project["id"]), headers=other["headers"])
    assert r.status_code == 403


# ---------- read and list ----------

def test_task_visibility(client, admin, manager, member, outsider, task):
    url = f"{API}/tasks/{task['id']}"
    for user, expected in ((admin, 200), (manager, 200), (member, 200), (outsider, 403)):
        assert client.get(url, headers=user["headers"]).status_code == expected, user["email"]
    assert client.get(f"{API}/tasks/9999", headers=admin["headers"]).status_code == 404


def test_filters_and_search(client, manager, member, four_tasks):
    h = manager["headers"]
    assert list_titles(client, h, priority="CRITICAL") == ["Fix login bug"]
    assert list_titles(client, h, search="homepage") == ["Design homepage"]
    assert sorted(list_titles(client, h, assigned_to=member["id"])) == ["Design homepage", "Fix login bug"]

    write_id = four_tasks["Write content"]["id"]
    client.patch(f"{API}/tasks/{write_id}/status", json={"status": "IN_PROGRESS"}, headers=h)
    assert list_titles(client, h, status="IN_PROGRESS") == ["Write content"]
    assert len(list_titles(client, h, status="TODO")) == 3


def test_sort_by_deadline_puts_tasks_without_deadline_last(client, manager, four_tasks):
    h = manager["headers"]
    asc = list_titles(client, h, sort_by="deadline", order="asc")
    assert asc == ["Fix login bug", "Design homepage", "Write content", "Setup hosting"]
    desc = list_titles(client, h, sort_by="deadline", order="desc")
    assert desc == ["Write content", "Design homepage", "Fix login bug", "Setup hosting"]


def test_task_pagination(client, manager, four_tasks):
    params = {"size": 3, "sort_by": "deadline", "order": "asc"}
    page1 = client.get(f"{API}/tasks", params={**params, "page": 1}, headers=manager["headers"]).json()
    page2 = client.get(f"{API}/tasks", params={**params, "page": 2}, headers=manager["headers"]).json()
    assert (page1["total"], page1["pages"]) == (4, 2)
    assert (len(page1["items"]), len(page2["items"])) == (3, 1)
    ids = [t["id"] for t in page1["items"] + page2["items"]]
    assert len(set(ids)) == 4  # no task repeated or skipped between pages


@pytest.mark.parametrize(
    "params",
    [{"sort_by": "title"}, {"status": "DONE"}, {"size": 0}],
)
def test_bad_list_parameters_are_rejected(client, manager, params):
    assert client.get(f"{API}/tasks", params=params, headers=manager["headers"]).status_code == 422


def test_task_list_shows_only_my_projects(client, member, outsider, task):
    assert client.get(f"{API}/tasks", headers=member["headers"]).json()["total"] == 1
    assert client.get(f"{API}/tasks", headers=outsider["headers"]).json()["total"] == 0


def test_my_tasks_shows_only_tasks_assigned_to_me(client, manager, member, four_tasks):
    r = client.get(f"{API}/tasks/my", headers=member["headers"])
    assert r.status_code == 200, r.text  # also proves "/my" is not read as a task id
    assert [t["title"] for t in r.json()["items"]] == ["Fix login bug", "Design homepage"]
    assert client.get(f"{API}/tasks/my", headers=manager["headers"]).json()["total"] == 0


# ---------- update ----------

def test_manager_updates_a_task(client, manager, task):
    r = client.put(f"{API}/tasks/{task['id']}", json={"title": "New title"}, headers=manager["headers"])
    assert r.status_code == 200
    assert r.json()["title"] == "New title"
    assert r.json()["updated_by"] == manager["id"]


def test_task_update_rules(client, manager, member, task):
    url = f"{API}/tasks/{task['id']}"
    h = manager["headers"]
    assert client.put(url, json={}, headers=h).status_code == 400
    assert client.put(url, json={"title": None}, headers=h).status_code == 422
    assert client.put(url, json={"deadline": days_from_today(-1)}, headers=h).status_code == 422
    assert client.put(url, json={"deadline": days_from_today(120)}, headers=h).status_code == 400
    assert client.put(url, json={"title": "Hacked"}, headers=member["headers"]).status_code == 403


# ---------- status, priority, assign, delete ----------

def test_assignee_can_change_the_status_of_their_own_task(client, member, task):
    r = client.patch(f"{API}/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}, headers=member["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "IN_PROGRESS"
    assert r.json()["updated_by"] == member["id"]


def test_member_cannot_change_the_status_of_someone_elses_task(client, manager, member, project):
    other = client.post(
        f"{API}/tasks", json=task_payload(project["id"], title="Not for member"), headers=manager["headers"]
    ).json()
    r = client.patch(f"{API}/tasks/{other['id']}/status", json={"status": "REVIEW"}, headers=member["headers"])
    assert r.status_code == 403
    assert r.json()["detail"] == "You can change the status only of tasks assigned to you"


def test_status_change_rules(client, manager, outsider, task):
    url = f"{API}/tasks/{task['id']}/status"
    h = manager["headers"]
    assert client.patch(url, json={"status": "DONE"}, headers=h).status_code == 422
    assert client.patch(url, json={"status": "TODO"}, headers=h).status_code == 400  # already TODO
    assert client.patch(url, json={"status": "REVIEW"}, headers=outsider["headers"]).status_code == 403
    assert client.patch(f"{API}/tasks/9999/status", json={"status": "REVIEW"}, headers=h).status_code == 404
    assert client.patch(url, json={"status": "COMPLETED"}, headers=h).status_code == 200


def test_priority_change(client, manager, member, task):
    url = f"{API}/tasks/{task['id']}/priority"  # the task starts as HIGH
    assert client.patch(url, json={"priority": "CRITICAL"}, headers=member["headers"]).status_code == 403
    assert client.patch(url, json={"priority": "CRITICAL"}, headers=manager["headers"]).status_code == 200
    assert client.patch(url, json={"priority": "CRITICAL"}, headers=manager["headers"]).status_code == 400


def test_assign_a_task(client, manager, member, outsider, project):
    h = manager["headers"]
    created = client.post(f"{API}/tasks", json=task_payload(project["id"], title="Unassigned"), headers=h).json()
    url = f"{API}/tasks/{created['id']}/assign"

    assert client.patch(url, json={"assigned_to": outsider["id"]}, headers=h).status_code == 400
    r = client.patch(url, json={"assigned_to": member["id"]}, headers=h)
    assert r.status_code == 200
    assert r.json()["assigned_to"] == member["id"]
    assert client.patch(url, json={"assigned_to": member["id"]}, headers=h).status_code == 400  # already
    assert client.patch(url, json={"assigned_to": member["id"]}, headers=member["headers"]).status_code == 403


def test_delete_a_task_is_a_soft_delete(client, manager, member, task):
    url = f"{API}/tasks/{task['id']}"
    assert client.delete(url, headers=member["headers"]).status_code == 403
    assert client.delete(url, headers=manager["headers"]).status_code == 204
    assert client.get(url, headers=manager["headers"]).status_code == 404
    assert client.get(f"{API}/tasks", headers=manager["headers"]).json()["total"] == 0