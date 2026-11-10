from tests.helpers import API

NEW = {"full_name": "Priya Sharma", "email": "priya@test.com", "password": "Password123"}


# ---------- list ----------

def test_admin_lists_users_with_pagination(client, admin, manager, member):
    r = client.get(f"{API}/users", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert (body["total"], body["page"], body["size"], body["pages"]) == (3, 1, 10, 1)

    r = client.get(f"{API}/users", params={"size": 2, "page": 2}, headers=admin["headers"])
    body = r.json()
    assert body["pages"] == 2
    assert len(body["items"]) == 1


def test_user_list_never_exposes_passwords(client, admin):
    r = client.get(f"{API}/users", headers=admin["headers"])
    assert "password" not in r.text.lower()


def test_user_search_and_filters(client, admin, manager, member):
    def total(**params):
        r = client.get(f"{API}/users", params=params, headers=admin["headers"])
        assert r.status_code == 200, r.text
        return r.json()["total"]

    assert total(search="manager") == 1
    assert total(search="MEMBER") == 1          # not case sensitive
    assert total(search="@test.com") == 3
    assert total(role="team_member") == 1
    assert total(role="admin") == 1
    assert total(is_active="true") == 3
    assert total(is_active="false") == 0


def test_page_size_is_limited(client, admin):
    r = client.get(f"{API}/users", params={"size": 1000}, headers=admin["headers"])
    assert r.status_code == 422


def test_only_admin_and_manager_can_list_users(client, manager, member):
    assert client.get(f"{API}/users", headers=manager["headers"]).status_code == 200
    r = client.get(f"{API}/users", headers=member["headers"])
    assert r.status_code == 403
    assert r.json()["detail"] == "You do not have permission to do this"


# ---------- create / read ----------

def test_admin_creates_a_user_with_a_role(client, admin):
    r = client.post(f"{API}/users", json={**NEW, "role": "project_manager"}, headers=admin["headers"])
    assert r.status_code == 201, r.text
    assert r.json()["role"]["name"] == "project_manager"


def test_created_user_defaults_to_team_member(client, admin):
    r = client.post(f"{API}/users", json=NEW, headers=admin["headers"])
    assert r.status_code == 201
    assert r.json()["role"]["name"] == "team_member"


def test_only_admin_can_create_users(client, manager, member):
    for user in (manager, member):
        r = client.post(f"{API}/users", json=NEW, headers=user["headers"])
        assert r.status_code == 403


def test_create_user_with_a_taken_email(client, admin, member):
    r = client.post(f"{API}/users", json={**NEW, "email": member["email"]}, headers=admin["headers"])
    assert r.status_code == 409


def test_get_one_user_is_admin_only(client, admin, member):
    assert client.get(f"{API}/users/{member['id']}", headers=admin["headers"]).status_code == 200
    assert client.get(f"{API}/users/9999", headers=admin["headers"]).status_code == 404
    assert client.get(f"{API}/users/{member['id']}", headers=member["headers"]).status_code == 403


# ---------- update profile ----------

def test_user_updates_own_profile(client, member):
    r = client.put(f"{API}/users/{member['id']}", json={"full_name": "New Name"}, headers=member["headers"])
    assert r.status_code == 200
    assert r.json()["full_name"] == "New Name"


def test_user_cannot_update_someone_else(client, member, outsider):
    r = client.put(f"{API}/users/{outsider['id']}", json={"full_name": "Hacked"}, headers=member["headers"])
    assert r.status_code == 403
    assert r.json()["detail"] == "You can update only your own profile"


def test_admin_can_update_anyone(client, admin, member):
    r = client.put(f"{API}/users/{member['id']}", json={"full_name": "By Admin"}, headers=admin["headers"])
    assert r.status_code == 200


def test_profile_update_cannot_change_role_or_status(client, member):
    # "mass assignment" attack: extra fields must be ignored
    r = client.put(
        f"{API}/users/{member['id']}",
        json={"full_name": "New Name", "role_id": 1, "is_active": False},
        headers=member["headers"],
    )
    assert r.status_code == 200
    assert r.json()["role"]["name"] == "team_member"
    assert r.json()["is_active"] is True


def test_profile_update_rejects_null_and_duplicate_email(client, member, outsider):
    url = f"{API}/users/{member['id']}"
    assert client.put(url, json={"full_name": None}, headers=member["headers"]).status_code == 422
    r = client.put(url, json={"email": outsider["email"]}, headers=member["headers"])
    assert r.status_code == 409


# ---------- status and role ----------

def test_admin_deactivates_and_reactivates_a_user(client, admin, member):
    url = f"{API}/users/{member['id']}/status"
    r = client.patch(url, json={"is_active": False}, headers=admin["headers"])
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # the old token stops working at once, and login is blocked
    assert client.get(f"{API}/auth/me", headers=member["headers"]).status_code == 401
    login = client.post(f"{API}/auth/login", data={"username": member["email"], "password": member["password"]})
    assert login.status_code == 403

    client.patch(url, json={"is_active": True}, headers=admin["headers"])
    assert client.get(f"{API}/auth/me", headers=member["headers"]).status_code == 200


def test_status_change_rules(client, admin, manager, member):
    own = f"{API}/users/{admin['id']}/status"
    assert client.patch(own, json={"is_active": False}, headers=admin["headers"]).status_code == 400
    other = f"{API}/users/{member['id']}/status"
    assert client.patch(other, json={"is_active": False}, headers=manager["headers"]).status_code == 403
    assert client.patch(f"{API}/users/9999/status", json={"is_active": False}, headers=admin["headers"]).status_code == 404


def test_admin_changes_a_role(client, admin, member):
    url = f"{API}/users/{member['id']}/role"
    r = client.patch(url, json={"role": "project_manager"}, headers=admin["headers"])
    assert r.status_code == 200
    assert r.json()["role"]["name"] == "project_manager"


def test_role_change_rules(client, admin, manager, member):
    url = f"{API}/users/{member['id']}/role"
    assert client.patch(url, json={"role": "banana"}, headers=admin["headers"]).status_code == 422
    assert client.patch(url, json={"role": "admin"}, headers=manager["headers"]).status_code == 403
    own = f"{API}/users/{admin['id']}/role"
    assert client.patch(own, json={"role": "team_member"}, headers=admin["headers"]).status_code == 400