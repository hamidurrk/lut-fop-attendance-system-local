PRAGMA foreign_keys = OFF;

-- Restructure attendance_sessions to inline descriptive fields
ALTER TABLE attendance_sessions RENAME TO attendance_sessions_old;

CREATE TABLE attendance_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_code    TEXT NOT NULL,
    week_number     INTEGER NOT NULL CHECK (week_number BETWEEN 1 AND 14),
    weekday_index   INTEGER NOT NULL CHECK (weekday_index BETWEEN 1 AND 5),
    start_hour      INTEGER NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
    end_hour        INTEGER NOT NULL CHECK (end_hour BETWEEN 1 AND 24),
    campus_name     TEXT NOT NULL,
    room_code       TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    status          TEXT NOT NULL DEFAULT 'pending',
    UNIQUE (chapter_code, week_number, weekday_index, start_hour, end_hour, campus_name, room_code)
);

INSERT INTO attendance_sessions (
    id,
    chapter_code,
    week_number,
    weekday_index,
    start_hour,
    end_hour,
    campus_name,
    room_code,
    created_at,
    status
)
SELECT
    s.id,
    COALESCE(c.code, 'Unknown chapter'),
    s.week_number,
    s.weekday_index,
    s.start_hour,
    s.end_hour,
    COALESCE(cp.name, 'Unknown campus'),
    COALESCE(r.code, 'Unknown room'),
    s.created_at,
    s.status
FROM attendance_sessions_old AS s
LEFT JOIN chapters AS c ON s.chapter_id = c.id
LEFT JOIN campuses AS cp ON s.campus_id = cp.id
LEFT JOIN rooms AS r ON s.room_id = r.id;

DROP TABLE attendance_sessions_old;

-- Restructure attendance_records to embed student identity
ALTER TABLE attendance_records RENAME TO attendance_records_old;

CREATE TABLE attendance_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    student_id          TEXT NOT NULL,
    student_name        TEXT,
    recorded_at         TEXT NOT NULL DEFAULT (datetime('now')),
    source              TEXT NOT NULL DEFAULT 'manual',
    raw_payload         TEXT,
    UNIQUE (session_id, student_id),
    FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE
);

INSERT INTO attendance_records (
    id,
    session_id,
    student_id,
    student_name,
    recorded_at,
    source,
    raw_payload
)
SELECT
    ar.id,
    ar.session_id,
    COALESCE(st.student_code, ar.student_id),
    NULLIF(TRIM(COALESCE(st.first_name, '') || ' ' || COALESCE(st.last_name, '')), ''),
    ar.recorded_at,
    ar.source,
    ar.raw_payload
FROM attendance_records_old AS ar
LEFT JOIN students AS st ON ar.student_id = st.id;

DROP TABLE attendance_records_old;

CREATE INDEX IF NOT EXISTS idx_attendance_records_session ON attendance_records(session_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_student ON attendance_records(student_id);

-- Remove obsolete tables
DROP TABLE IF EXISTS qr_scan_events;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS campuses;
DROP TABLE IF EXISTS chapters;
DROP TABLE IF EXISTS students;

PRAGMA foreign_keys = ON;
