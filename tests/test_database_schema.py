from __future__ import annotations

from pathlib import Path

from attendance_app.data import Database


def test_initialize_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "attendance.db"
    database = Database(db_path)
    database.initialize()

    with database.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    expected_tables = {
        "attendance_sessions",
        "attendance_records",
        "session_templates",
        "auto_grader_runs",
        "bonus_records",
        "schema_migrations",
    }

    assert expected_tables.issubset(tables)
