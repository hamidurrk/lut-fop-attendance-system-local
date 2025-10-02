from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        migrations_dir = Path(__file__).resolve().parent / "migrations"
        migration_files = sorted(migrations_dir.glob("*.sql"))

        with self.connect() as connection:
            self._ensure_migrations_table(connection)
            applied = {
                row["name"] for row in connection.execute("SELECT name FROM schema_migrations")
            }

            for migration in migration_files:
                if migration.name in applied:
                    continue
                with migration.open("r", encoding="utf-8") as sql_file:
                    sql_script = sql_file.read()
                connection.executescript(sql_script)
                connection.execute(
                    "INSERT INTO schema_migrations(name) VALUES (?)",
                    (migration.name,),
                )

    @staticmethod
    def _ensure_migrations_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
