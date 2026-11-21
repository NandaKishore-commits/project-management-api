from tests.helpers import API


def inbox(client, user, **params):
    r = client.get(f"{API}/notifications", params=params, headers=user["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def unread(client, user):
    return client.get(f"{API}/notifications/unread-count", headers=user["headers"]).json()["unread"]


def types_for(client, user):
    return [n["type"] for n in inbox(client, user)["items"]]


def add_to_project(client, manager, project, user):
    r = client.post(
        f"{API}/projects/{project['id']}/members", json={"user_id": user["id"]}, headers=manager["headers"]
    )
    assert r.status_code == 201, r.text


def test_assignee_is_notified_when_a_task_is_created_for_him(client, member, task):
    body = inbox(client, member)
    assert body["total"] == 1
    note = body["items"][0]
    assert note["type"] == "TASK_ASSIGNED"
    assert note["task_id"] == task["id"]
    assert note["is_read"] is False


def test_you_are_not_notified_about_your_own_actions(client, manager, task):
    assert inbox(client, manager)["total"] == 0


def test_unread_count_and_mark_one_read(client, member, task):
    assert unread(client, member) == 1
    note_id = inbox(client, member)["items"][0]["id"]

    r = client.patch(f"{API}/notifications/{note_id}/read", headers=member["headers"])
    assert r.status_code == 200
    assert r.json()["is_read"] is True
    assert r.json()["read_at"] is not None

    assert unread(client, member) == 0
    assert inbox(client, member, is_read="false")["total"] == 0
    assert inbox(client, member, is_read="true")["total"] == 1


def test_mark_all_read(client, manager, member, task):
    for new_status in ("IN_PROGRESS", "REVIEW"):
        r = client.patch(
            f"{API}/tasks/{task['id']}/status", json={"status": new_status}, headers=manager["headers"]
        )
        assert r.status_code == 200, r.text
    assert unread(client, member) == 3  # assigned + two status changes

    r = client.patch(f"{API}/notifications/read-all", headers=member["headers"])
    assert r.status_code == 200
    assert r.json() == {"updated": 3}
    assert unread(client, member) == 0


def test_notifications_are_private(client, manager, member, task):
    note_id = inbox(client, member)["items"][0]["id"]
    assert client.patch(f"{API}/notifications/{note_id}/read", headers=manager["headers"]).status_code == 404
    assert client.patch(f"{API}/notifications/9999/read", headers=member["headers"]).status_code == 404
    assert client.get(f"{API}/notifications").status_code == 401


def test_watchers_and_assignee_are_notified_of_comments(client, make_user, manager, member, project, task):
    watcher = make_user("watcher@test.com")
    add_to_project(client, manager, project, watcher)
    client.post(
        f"{API}/tasks/{task['id']}/watchers", json={"user_id": watcher["id"]}, headers=watcher["headers"]
    )

    r = client.post(
        f"{API}/tasks/{task['id']}/comments", json={"content": "Looks good"}, headers=manager["headers"]
    )
    assert r.status_code == 201, r.text

    assert "COMMENT_ADDED" in types_for(client, watcher)
    assert "COMMENT_ADDED" in types_for(client, member)
    assert "COMMENT_ADDED" not in types_for(client, manager)  # the author is not notified


def test_reassignment_notifies_the_old_and_the_new_assignee(client, make_user, manager, member, project, task):
    other = make_user("other@test.com")
    add_to_project(client, manager, project, other)

    r = client.patch(
        f"{API}/tasks/{task['id']}/assign",
        json={"assigned_to": other["id"], "reason": "More capacity"},
        headers=manager["headers"],
    )
    assert r.status_code == 200, r.text

    assert types_for(client, other) == ["TASK_ASSIGNED"]
    assert "TASK_REASSIGNED" in types_for(client, member)
    assert "More capacity" in inbox(client, member)["items"][0]["message"]