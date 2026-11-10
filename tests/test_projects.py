from app.utils.enums import RoleName
from tests.helpers import API, days_from_today, project_payload, task_payload


# ---------- create ----------

def test_manager_creates_project_and_becomes_member(client, manager):
    r = client.post(f"{API}/projects", json=project_payload(), headers=manager["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "ACTIVE"
    assert body["created_by"] == manager["id"]

    members = client.get(f"{API}/projects/{body['id']}/members", headers=manager["headers"]).json()
    assert [m["user_id"] for m in members] == [manager["id"]]


def test_team_member_cannot_create_a_project(client, member):
    r = client.post(f"{API}/projects", json=project_payload(), headers=member["headers"])
    assert r.status_code == 403


def test_project_dates_and_name_are_validated(client, manager):
    h = manager["headers"]
    bad_dates = project_payload(start_date=days_from_today(10), end_date=days_from_today(1))
    r = client.post(f"{API}/projects", json=bad_dates, headers=h)
    assert r.status_code == 422
    assert {"field": "body", "message": "end_date must be after start_date"} in r.json()["errors"]

    r = client.post(f"{API}/projects", json=project_payload(name="AB"), headers=h)
    assert r.status_code == 422


# ---------- read ----------

def test_project_visibility(client, admin, manager, member, outsider, project):
    url = f"{API}/projects/{project['id']}"
    for user, expected in ((admin, 200), (manager, 200), (member, 200), (outsider, 403)):
        assert client.get(url, headers=user["headers"]).status_code == expected, user["email"]
    assert client.get(f"{API}/projects/9999", headers=admin["headers"]).status_code == 404


def test_project_list_shows_only_my_projects(client, admin, member, outsider, project):
    def total(user):
        return client.get(f"{API}/projects", headers=user["headers"]).json()["total"]

    assert (total(admin), total(member), total(outsider)) == (1, 1, 0)


def test_project_search_filter_and_pagination(client, manager):
    h = manager["headers"]
    ids = {}
    for name in ("Alpha Site", "Beta App", "Gamma Tool"):
        r = client.post(f"{API}/projects", json=project_payload(name=name), headers=h)
        ids[name] = r.json()["id"]
    client.put(f"{API}/projects/{ids['Beta App']}", json={"status": "ON_HOLD"}, headers=h)

    def total(**params):
        return client.get(f"{API}/projects", params=params, headers=h).json()["total"]

    assert total(search="beta") == 1
    assert total(status="ON_HOLD") == 1
    assert total(status="ACTIVE") == 2

    page = client.get(f"{API}/projects", params={"size": 2}, headers=h).json()
    assert page["pages"] == 2
    assert len(page["items"]) == 2


# ---------- update and delete ----------

def test_manager_updates_a_project(client, manager, project):
    r = client.put(
        f"{API}/projects/{project['id']}",
        json={"name": "Renamed", "status": "ON_HOLD"},
        headers=manager["headers"],
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["status"] == "ON_HOLD"


def test_project_update_rules(client, manager, project):
    url = f"{API}/projects/{project['id']}"
    h = manager["headers"]
    assert client.put(url, json={}, headers=h).status_code == 400
    assert client.put(url, json={"name": None}, headers=h).status_code == 422
    assert client.put(url, json={"status": "banana"}, headers=h).status_code == 422
    # only one date sent: the endpoint compares it with the saved date (400)
    assert client.put(url, json={"end_date": days_from_today(-5)}, headers=h).status_code == 400
    # both dates sent: the schema catches it (422)
    both = {"start_date": days_from_today(50), "end_date": days_from_today(10)}
    assert client.put(url, json=both, headers=h).status_code == 422


def test_only_managers_of_the_project_can_change_it(client, make_user, admin, member, project):
    other_manager = make_user("manager2@test.com", RoleName.PROJECT_MANAGER)
    url = f"{API}/projects/{project['id']}"

    r = client.put(url, json={"name": "Hacked"}, headers=other_manager["headers"])
    assert r.status_code == 403
    assert r.json()["detail"] == "You can manage only projects you belong to"
    assert client.delete(url, headers=other_manager["headers"]).status_code == 403
    assert client.put(url, json={"name": "Hacked"}, headers=member["headers"]).status_code == 403
    # the admin can manage any project
    assert client.put(url, json={"name": "By Admin"}, headers=admin["headers"]).status_code == 200


def test_delete_is_a_soft_delete_and_hides_the_tasks(client, manager, project, task):
    url = f"{API}/projects/{project['id']}"
    r = client.delete(url, headers=manager["headers"])
    assert r.status_code == 204
    assert r.content == b""

    assert client.get(url, headers=manager["headers"]).status_code == 404
    assert client.get(f"{API}/tasks/{task['id']}", headers=manager["headers"]).status_code == 404
    assert client.get(f"{API}/projects", headers=manager["headers"]).json()["total"] == 0


# ---------- members ----------

def test_add_and_list_members(client, manager, member, outsider, project):
    pid = project["id"]
    r = client.post(f"{API}/projects/{pid}/members", json={"user_id": outsider["id"]}, headers=manager["headers"])
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == outsider["email"]

    members = client.get(f"{API}/projects/{pid}/members", headers=member["headers"]).json()
    assert len(members) == 3  # manager (creator), member, outsider


def test_member_rules(client, make_user, manager, member, outsider, project):
    url = f"{API}/projects/{project['id']}/members"
    h = manager["headers"]
    assert client.post(url, json={"user_id": member["id"]}, headers=h).status_code == 409
    assert client.post(url, json={"user_id": 9999}, headers=h).status_code == 404

    inactive = make_user("gone@test.com", is_active=False)
    assert client.post(url, json={"user_id": inactive["id"]}, headers=h).status_code == 404
    # a team member cannot add people
    assert client.post(url, json={"user_id": outsider["id"]}, headers=member["headers"]).status_code == 403


def test_removing_a_member_unassigns_their_tasks(client, manager, member, project, task):
    pid = project["id"]
    assert task["assigned_to"] == member["id"]

    r = client.delete(f"{API}/projects/{pid}/members/{member['id']}", headers=manager["headers"])
    assert r.status_code == 204

    updated = client.get(f"{API}/tasks/{task['id']}", headers=manager["headers"]).json()
    assert updated["assigned_to"] is None
    assert client.get(f"{API}/projects/{pid}", headers=member["headers"]).status_code == 403


def test_cannot_remove_the_creator_or_a_non_member(client, manager, outsider, project):
    base = f"{API}/projects/{project['id']}/members"
    assert client.delete(f"{base}/{manager['id']}", headers=manager["headers"]).status_code == 400
    assert client.delete(f"{base}/{outsider['id']}", headers=manager["headers"]).status_code == 404


# ---------- stats ----------

def test_project_stats_and_progress(client, manager, project):
    h = manager["headers"]
    ids = []
    for title in ("Task A", "Task B", "Task C", "Task D"):
        r = client.post(f"{API}/tasks", json=task_payload(project["id"], title=title), headers=h)
        ids.append(r.json()["id"])
    client.patch(f"{API}/tasks/{ids[0]}/status", json={"status": "COMPLETED"}, headers=h)
    client.patch(f"{API}/tasks/{ids[1]}/status", json={"status": "IN_PROGRESS"}, headers=h)

    r = client.get(f"{API}/projects/{project['id']}/stats", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total_tasks"] == 4
    assert body["by_status"] == {"TODO": 2, "IN_PROGRESS": 1, "REVIEW": 0, "COMPLETED": 1}
    assert body["progress_percent"] == 25.0


def test_stats_of_an_empty_project_do_not_divide_by_zero(client, manager, project):
    body = client.get(f"{API}/projects/{project['id']}/stats", headers=manager["headers"]).json()
    assert body["total_tasks"] == 0
    assert body["progress_percent"] == 0.0


def test_stats_are_private_to_project_members(client, outsider, project):
    r = client.get(f"{API}/projects/{project['id']}/stats", headers=outsider["headers"])
    assert r.status_code == 403