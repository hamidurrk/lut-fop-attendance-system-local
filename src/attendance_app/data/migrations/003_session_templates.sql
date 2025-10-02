PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS session_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campus_name     TEXT NOT NULL,
    weekday_index   INTEGER NOT NULL CHECK (weekday_index BETWEEN 1 AND 5),
    room_code       TEXT NOT NULL,
    start_hour      INTEGER NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    end_hour        INTEGER NOT NULL CHECK (end_hour BETWEEN 1 AND 24),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (campus_name, weekday_index, room_code, start_hour, end_hour)
);
