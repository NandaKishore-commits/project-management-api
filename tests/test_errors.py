from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.main import app
from tests.helpers import API


@contextmanager
def temporary_route(path, endpoint):
    """Adds a route for one test, then removes it. Crashes become responses instead of exceptions."""
    app.add_api_route(path, endpoint)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.router.routes.pop()


PROTECTED = ["/auth/me", "/users", "/projects", "/tasks", "/tasks/my", "/dashboard/stats"]


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_endpoints_need_a_token(client, path):
    r = client.get(f"{API}{path}")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_health_check_and_request_id_header(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert len(r.headers["x-request-id"]) == 8


def test_unknown_url_returns_a_json_404(client):
    r = client.get("/nothing")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_validation_error_names_the_field(client, admin):
    r = client.get(f"{API}/users", params={"size": "abc"}, headers=admin["headers"])
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "size"


def test_unexpected_crash_returns_a_safe_500():
    def crash():
        raise ZeroDivisionError("internal secret detail")

    with temporary_route("/__crash", crash) as test_client:
        r = test_client.get("/__crash")

    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == r.headers["x-request-id"]
    assert "internal secret detail" not in r.text   # no internals leak to the client
    assert "Traceback" not in r.text


def test_database_conflict_returns_409():
    def conflict():
        raise IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed: users.email"))

    with temporary_route("/__conflict", conflict) as test_client:
        r = test_client.get("/__conflict")

    assert r.status_code == 409
    assert "UNIQUE" not in r.text   # the database's own wording is never shown


def test_database_down_returns_503():
    def down():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    with temporary_route("/__down", down) as test_client:
        r = test_client.get("/__down")

    assert r.status_code == 503
    assert "connection refused" not in r.text