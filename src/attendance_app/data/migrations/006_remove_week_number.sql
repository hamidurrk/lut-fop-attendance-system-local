PRAGMA foreign_keys = OFF;

ALTER TABLE attendance_sessions RENAME TO attendance_sessions_with_week;

CREATE TABLE attendance_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_code    TEXT NOT NULL,
    weekday_index   INTEGER NOT NULL CHECK (weekday_index BETWEEN 1 AND 5),
    start_hour      INTEGER NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    end_hour        INTEGER NOT NULL CHECK (end_hour BETWEEN 1 AND 24),
    campus_name     TEXT NOT NULL,
    room_code       TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    status          TEXT NOT NULL DEFAULT 'pending',
    UNIQUE (chapter_code, weekday_index, start_hour, end_hour, campus_name, room_code)
);

INSERT OR IGNORE INTO attendance_sessions (
    id,
    chapter_code,
    weekday_index,
    start_hour,
    end_hour,
    campus_name,
    room_code,
    created_at,
    status
)
SELECT
    id,
    chapter_code,
    weekday_index,
    start_hour,
    end_hour,
    campus_name,
    room_code,
    created_at,
    status
FROM attendance_sessions_with_week;

DROP TABLE attendance_sessions_with_week;

PRAGMA foreign_keys = ON;
