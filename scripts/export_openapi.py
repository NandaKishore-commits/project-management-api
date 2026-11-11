"""Writes the API description to docs/openapi.json.

Run from the project root:  python -m scripts.export_openapi
"""
import json
from pathlib import Path

from app.main import app

DOCS_DIR = Path("docs")


def run() -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    schema = app.openapi()
    (DOCS_DIR / "openapi.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Wrote docs/openapi.json")


if __name__ == "__main__":
    run()