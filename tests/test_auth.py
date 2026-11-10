from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from tests.helpers import API

NEW_USER = {"full_name": "Ravi Kumar", "email": "ravi@test.com", "password": "Password123"}


def login(client, email, password):
    return client.post(f"{API}/auth/login", data={"username": email, "password": password})


def token_headers(payload_extra: dict, key: str, minutes: int = 60) -> dict:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    token = jwt.encode({**payload_extra, "exp": exp}, key, algorithm=settings.ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


# ---------- register ----------

def test_register_creates_team_member(client):
    r = client.post(f"{API}/auth/register", json=NEW_USER)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "ravi@test.com"
    assert body["role"]["name"] == "team_member"
    assert body["is_active"] is True


def test_register_never_returns_the_password(client):
    r = client.post(f"{API}/auth/register", json=NEW_USER)
    assert "password" not in r.json()
    assert "hashed_password" not in r.json()
    assert "Password123" not in r.text


def test_register_cannot_choose_a_role(client):
    r = client.post(f"{API}/auth/register", json={**NEW_USER, "role": "admin"})
    assert r.status_code == 201
    assert r.json()["role"]["name"] == "team_member"


def test_register_duplicate_email_is_case_insensitive(client):
    assert client.post(f"{API}/auth/register", json=NEW_USER).status_code == 201
    r = client.post(f"{API}/auth/register", json={**NEW_USER, "email": "RAVI@Test.com"})
    assert r.status_code == 409
    assert r.json()["detail"] == "Email already registered"


def test_register_validation_errors_use_the_clean_format(client):
    r = client.post(
        f"{API}/auth/register",
        json={"full_name": "R", "email": "not-an-email", "password": "123"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["detail"] == "Validation failed"
    fields = {e["field"] for e in body["errors"]}
    assert {"full_name", "email", "password"} <= fields


@pytest.mark.parametrize("password", ["abcdefgh", "12345678"])
def test_register_rejects_weak_passwords(client, password):
    r = client.post(f"{API}/auth/register", json={**NEW_USER, "password": password})
    assert r.status_code == 422
    message = r.json()["errors"][0]["message"]
    assert "at least one letter and one number" in message


# ---------- login ----------

def test_login_returns_a_working_token(client, member):
    r = login(client, member["email"], member["password"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"

    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == member["email"]


def test_login_email_is_case_insensitive(client, member):
    assert login(client, member["email"].upper(), member["password"]).status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_error(client, member):
    wrong = login(client, member["email"], "WrongPass1")
    unknown = login(client, "nobody@test.com", "Password123")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Incorrect email or password"}


def test_deactivated_user_cannot_log_in(client, make_user):
    user = make_user("gone@test.com", is_active=False)
    r = login(client, user["email"], user["password"])
    assert r.status_code == 403
    assert r.json()["detail"] == "Your account is deactivated"


# ---------- tokens ----------

def test_deactivated_users_old_token_stops_working(client, make_user):
    user = make_user("gone@test.com", is_active=False)
    assert client.get(f"{API}/auth/me", headers=user["headers"]).status_code == 401


def test_me_needs_a_valid_token(client):
    r = client.get(f"{API}/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"

    r = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid or expired token"


def test_expired_token_is_rejected(client, member):
    headers = token_headers({"sub": str(member["id"])}, settings.SECRET_KEY, minutes=-1)
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401


def test_token_signed_with_another_key_is_rejected(client, member):
    headers = token_headers({"sub": str(member["id"])}, "x" * 64)
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401