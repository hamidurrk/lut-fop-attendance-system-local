PRAGMA foreign_keys = OFF;

ALTER TABLE attendance_records RENAME TO attendance_records_old;

CREATE TABLE attendance_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    student_id          TEXT NOT NULL,
    student_name        TEXT,
    recorded_at         TEXT NOT NULL DEFAULT (datetime('now')),
    source              TEXT NOT NULL DEFAULT 'manual',
    a_point             INTEGER NOT NULL DEFAULT 0,
    b_point             INTEGER NOT NULL DEFAULT 0,
    t_point             INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'recorded',
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
    a_point,
    b_point,
    t_point,
    status
)
SELECT
    id,
    session_id,
    student_id,
    student_name,
    recorded_at,
    source,
    CAST(ROUND(COALESCE(a_point, 0)) AS INTEGER),
    CAST(ROUND(COALESCE(b_point, 0)) AS INTEGER),
    CAST(ROUND(COALESCE(t_point, 0)) AS INTEGER),
    status
FROM attendance_records_old;

DROP TABLE attendance_records_old;

CREATE INDEX IF NOT EXISTS idx_attendance_records_session ON attendance_records(session_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_student ON attendance_records(student_id);

ALTER TABLE bonus_records RENAME TO bonus_records_old;

CREATE TABLE bonus_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    student_name    TEXT NOT NULL,
    b_point         INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE
);

INSERT INTO bonus_records (
    id,
    session_id,
    student_name,
    b_point,
    status
)
SELECT
    id,
    session_id,
    student_name,
    CAST(ROUND(COALESCE(b_point, 0)) AS INTEGER),
    status
FROM bonus_records_old;

DROP TABLE bonus_records_old;

CREATE INDEX IF NOT EXISTS idx_bonus_records_session ON bonus_records(session_id);

PRAGMA foreign_keys = ON;
