import pytest

from tests.helpers import API, task_payload


def comments_url(task):
    return f"{API}/tasks/{task['id']}/comments"


# ---------- comments ----------

def test_member_adds_a_comment(client, member, task):
    r = client.post(comments_url(task), json={"content": "Design is done."}, headers=member["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["content"] == "Design is done."
    assert body["user"]["email"] == member["email"]
    assert "password" not in str(body).lower()


def test_member_can_comment_on_any_task_in_his_project(client, manager, member, project):
    other = client.post(
        f"{API}/tasks", json=task_payload(project["id"], title="Not for member"), headers=manager["headers"]
    ).json()
    r = client.post(comments_url(other), json={"content": "Can I help?"}, headers=member["headers"])
    assert r.status_code == 201


@pytest.mark.parametrize("body", [{"content": ""}, {"content": "     "}, {}])
def test_invalid_comments_are_rejected(client, member, task, body):
    assert client.post(comments_url(task), json=body, headers=member["headers"]).status_code == 422


def test_comment_on_a_missing_task(client, member, task):
    r = client.post(f"{API}/tasks/9999/comments", json={"content": "Hello"}, headers=member["headers"])
    assert r.status_code == 404


def test_outsider_cannot_read_or_write_comments(client, outsider, task):
    h = outsider["headers"]
    assert client.post(comments_url(task), json={"content": "Hi"}, headers=h).status_code == 403
    assert client.get(comments_url(task), headers=h).status_code == 403
    assert client.get(f"{API}/tasks/{task['id']}/activity", headers=h).status_code == 403


def test_comments_are_listed_oldest_first(client, manager, member, task):
    for text in ("first", "second", "third"):
        client.post(comments_url(task), json={"content": text}, headers=member["headers"])

    r = client.get(comments_url(task), headers=manager["headers"])
    assert [c["content"] for c in r.json()["items"]] == ["first", "second", "third"]

    page = client.get(comments_url(task), params={"size": 2}, headers=manager["headers"]).json()
    assert (page["total"], page["pages"], len(page["items"])) == (3, 2, 2)


def test_comments_of_a_deleted_task_are_hidden(client, manager, task):
    client.delete(f"{API}/tasks/{task['id']}", headers=manager["headers"])
    assert client.get(comments_url(task), headers=manager["headers"]).status_code == 404
    assert client.get(f"{API}/tasks/{task['id']}/activity", headers=manager["headers"]).status_code == 404


# ---------- activity history ----------

def test_task_activity_records_who_did_what(client, manager, member, task):
    client.patch(f"{API}/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}, headers=member["headers"])

    r = client.get(f"{API}/tasks/{task['id']}/activity", headers=manager["headers"])
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["action"] for i in items] == ["STATUS_CHANGED", "TASK_ASSIGNED", "TASK_CREATED"]  # newest first

    assert items[0]["details"] == "TODO -> IN_PROGRESS"
    assert items[0]["user"]["email"] == member["email"]
    assert items[-1]["user"]["email"] == manager["email"]


def test_a_comment_is_logged_without_copying_its_text(client, member, task):
    client.post(comments_url(task), json={"content": "private words"}, headers=member["headers"])
    items = client.get(f"{API}/tasks/{task['id']}/activity", headers=member["headers"]).json()["items"]
    assert items[0]["action"] == "COMMENT_ADDED"
    assert "private words" not in str(items[0])


def test_project_activity_and_the_action_filter(client, member, project, task):
    client.patch(f"{API}/tasks/{task['id']}/status", json={"status": "IN_PROGRESS"}, headers=member["headers"])
    url = f"{API}/projects/{project['id']}/activity"

    items = client.get(url, headers=member["headers"]).json()["items"]
    actions = {i["action"] for i in items}
    assert {"PROJECT_CREATED", "MEMBER_ADDED", "TASK_CREATED", "STATUS_CHANGED"} <= actions

    only = client.get(url, params={"action": "STATUS_CHANGED"}, headers=member["headers"]).json()["items"]
    assert {i["action"] for i in only} == {"STATUS_CHANGED"}
    assert client.get(url, params={"action": "banana"}, headers=member["headers"]).status_code == 422


def test_project_activity_permissions(client, admin, outsider, project):
    url = f"{API}/projects/{project['id']}/activity"
    assert client.get(url, headers=outsider["headers"]).status_code == 403
    assert client.get(f"{API}/projects/9999/activity", headers=admin["headers"]).status_code == 404