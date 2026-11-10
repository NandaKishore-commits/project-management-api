from datetime import date, timedelta

from sqlalchemy import update

from app.models import Task
from app.utils.enums import RoleName
from tests.helpers import API, project_payload, task_payload


def get_stats(client, user):
    r = client.get(f"{API}/dashboard/stats", headers=user["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def test_dashboard_requires_login(client):
    assert client.get(f"{API}/dashboard/stats").status_code == 401


def test_admin_dashboard_counts(client, admin, task):
    stats = get_stats(client, admin)
    assert stats["total_projects"] == 1
    assert stats["total_tasks"] == 1
    assert stats["pending_tasks"] == 1
    assert stats["completed_tasks"] == 0
    assert stats["completion_percent"] == 0.0
    assert stats["by_status"] == {"TODO": 1, "IN_PROGRESS": 0, "REVIEW": 0, "COMPLETED": 0}
    assert stats["by_priority"] == {"LOW": 0, "MEDIUM": 0, "HIGH": 1, "CRITICAL": 0}
    # PROJECT_CREATED, MEMBER_ADDED, TASK_CREATED, TASK_ASSIGNED
    assert len(stats["recent_activity"]) == 4


def test_status_groups_add_up_to_the_total(client, manager, project, task):
    for status in ("IN_PROGRESS", "REVIEW", "COMPLETED"):
        created = client.post(
            f"{API}/tasks", json=task_payload(project["id"], title=f"Task {status}"), headers=manager["headers"]
        ).json()
        client.patch(f"{API}/tasks/{created['id']}/status", json={"status": status}, headers=manager["headers"])

    stats = get_stats(client, manager)
    assert stats["total_tasks"] == 4
    assert stats["pending_tasks"] == 1
    assert stats["in_progress_tasks"] == 2  # IN_PROGRESS + REVIEW
    assert stats["completed_tasks"] == 1
    assert stats["pending_tasks"] + stats["in_progress_tasks"] + stats["completed_tasks"] == stats["total_tasks"]
    assert stats["completion_percent"] == 25.0


def test_my_open_tasks(client, manager, member, task):
    assert get_stats(client, member)["my_open_tasks"] == 1
    assert get_stats(client, manager)["my_open_tasks"] == 0

    client.patch(f"{API}/tasks/{task['id']}/status", json={"status": "COMPLETED"}, headers=member["headers"])
    assert get_stats(client, member)["my_open_tasks"] == 0


def test_overdue_counts_only_unfinished_late_tasks(client, db_session, manager, task):
    # The API refuses past deadlines, so this one test edits the database directly
    db_session.execute(update(Task).where(Task.id == task["id"]).values(deadline=date.today() - timedelta(days=1)))
    db_session.commit()
    assert get_stats(client, manager)["overdue_tasks"] == 1

    client.patch(f"{API}/tasks/{task['id']}/status", json={"status": "COMPLETED"}, headers=manager["headers"])
    assert get_stats(client, manager)["overdue_tasks"] == 0


def test_dashboard_only_counts_my_projects(client, make_user, admin, member, project, task):
    other = make_user("manager2@test.com", RoleName.PROJECT_MANAGER)
    second = client.post(f"{API}/projects", json=project_payload(name="Other project"), headers=other["headers"]).json()
    client.post(f"{API}/tasks", json=task_payload(second["id"], title="Other task"), headers=other["headers"])

    assert get_stats(client, admin)["total_projects"] == 2
    assert get_stats(client, admin)["total_tasks"] == 2
    assert get_stats(client, member)["total_projects"] == 1
    assert get_stats(client, member)["total_tasks"] == 1
    assert get_stats(client, other)["total_tasks"] == 1


def test_user_without_projects_gets_zeros(client, outsider):
    stats = get_stats(client, outsider)
    assert stats["total_projects"] == 0
    assert stats["total_tasks"] == 0
    assert stats["completion_percent"] == 0.0
    assert stats["by_status"] == {"TODO": 0, "IN_PROGRESS": 0, "REVIEW": 0, "COMPLETED": 0}
    assert stats["recent_activity"] == []