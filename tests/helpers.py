from datetime import date, timedelta

API = "/api/v1"


def days_from_today(days: int) -> str:
    """A date as text. days_from_today(10) is ten days from now, e.g. '2026-11-20'.

    Tests use relative dates, so they never break when the calendar moves on.
    """
    return (date.today() + timedelta(days=days)).isoformat()


def project_payload(**overrides) -> dict:
    """A valid body for POST /projects. Pass keyword arguments to change a field."""
    data = {
        "name": "Website Redesign",
        "description": "Redesign the company website",
        "start_date": days_from_today(0),
        "end_date": days_from_today(90),
    }
    data.update(overrides)
    return data


def task_payload(project_id: int, **overrides) -> dict:
    """A valid body for POST /tasks. Pass keyword arguments to change a field."""
    data = {
        "title": "Design homepage",
        "priority": "HIGH",
        "deadline": days_from_today(10),
        "project_id": project_id,
    }
    data.update(overrides)
    return data