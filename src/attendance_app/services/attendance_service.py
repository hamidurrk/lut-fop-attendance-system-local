from __future__ import annotations

import sqlite3

from attendance_app.data import Database
from attendance_app.models import AttendanceSession, BonusRecord, SessionTemplate, Student


class DuplicateSessionError(RuntimeError):
    """Raised when attempting to create a duplicate attendance session."""


class DuplicateAttendanceError(RuntimeError):
    """Raised when a student has already been logged for the session."""


class AttendanceService:
    def __init__(self, database: Database) -> None:
        self._database = database

    def initialize(self) -> None:
        self._database.initialize()

    def start_session(self, session: AttendanceSession) -> int:
        with self._database.connect() as connection:
            duplicate = connection.execute(
                """
                SELECT id FROM attendance_sessions
                WHERE chapter_code = ?
                  AND week_number = ?
                  AND weekday_index = ?
                  AND start_hour = ?
                  AND end_hour = ?
                  AND campus_name = ?
                  AND room_code = ?
                """,
                (
                    session.chapter_code.strip(),
                    session.week_number,
                    session.weekday_index,
                    session.start_hour,
                    session.end_hour,
                    session.campus_name.strip(),
                    session.room_code.strip(),
                ),
            ).fetchone()

            if duplicate:
                raise DuplicateSessionError("An attendance session with these details already exists.")

            cursor = connection.execute(
                """
                INSERT INTO attendance_sessions (
                    chapter_code, week_number, weekday_index, start_hour, end_hour,
                    campus_name, room_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.chapter_code.strip(),
                    session.week_number,
                    session.weekday_index,
                    session.start_hour,
                    session.end_hour,
                    session.campus_name.strip(),
                    session.room_code.strip(),
                ),
            )
            return int(cursor.lastrowid)

    def record_attendance(
        self,
        session_id: int,
        student: Student,
        *,
        source: str = "manual",
        a_point: float | None = None,
        b_point: float | None = None,
        t_point: float | None = None,
        status: str = "recorded",
    ) -> int:
        student_identifier = student.student_code.strip()
        student_name = student.display_name if student.display_name != student.student_code else None
        a_value = float(a_point) if a_point is not None else 5.0
        b_value = float(b_point) if b_point is not None else 0.0
        total_value = float(t_point) if t_point is not None else a_value + b_value
        status_value = status.strip() if status else "recorded"

        with self._database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM attendance_records WHERE session_id = ? AND student_id = ?",
                (session_id, student_identifier),
            ).fetchone()

            if existing:
                raise DuplicateAttendanceError("Student already recorded for this session.")

            cursor = connection.execute(
                """
                INSERT INTO attendance_records (
                    session_id, student_id, student_name, source, a_point, b_point, t_point, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    student_identifier,
                    student_name,
                    source,
                    a_value,
                    b_value,
                    total_value,
                    status_value,
                ),
            )
            return int(cursor.lastrowid)

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, chapter_code, week_number, weekday_index,
                       start_hour, end_hour, campus_name, room_code, created_at
                  FROM attendance_sessions
              ORDER BY created_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_attendance_records(self, limit: int = 10) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT ar.id,
                       ar.session_id,
                       ar.student_id,
                       ar.student_name,
                       ar.recorded_at,
                       ar.source,
                       ar.a_point,
                       ar.b_point,
                       ar.t_point,
                       ar.status,
                       s.chapter_code,
                       s.week_number,
                       s.campus_name,
                       s.room_code,
                       s.start_hour,
                       s.end_hour
                  FROM attendance_records AS ar
            INNER JOIN attendance_sessions AS s ON s.id = ar.session_id
              ORDER BY datetime(ar.recorded_at) DESC, ar.id DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def recent_attendance_for_session(self, session_id: int, limit: int = 10) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT ar.id,
                       ar.session_id,
                       ar.student_id,
                       ar.student_name,
                       ar.recorded_at,
                       ar.source,
                       ar.a_point,
                       ar.b_point,
                       ar.t_point,
                       ar.status
                  FROM attendance_records AS ar
                 WHERE ar.session_id = ?
              ORDER BY datetime(ar.recorded_at) DESC, ar.id DESC
                 LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def list_session_templates(self) -> list[SessionTemplate]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, campus_name, weekday_index, room_code, start_hour, end_hour
                  FROM session_templates
              ORDER BY campus_name, room_code, weekday_index, start_hour
                """
            ).fetchall()

        return [
            SessionTemplate(
                id=int(row["id"]),
                campus_name=row["campus_name"],
                weekday_index=int(row["weekday_index"]),
                room_code=row["room_code"],
                start_hour=int(row["start_hour"]),
                end_hour=int(row["end_hour"]),
            )
            for row in rows
        ]

    def record_bonus(
        self,
        bonus: BonusRecord,
    ) -> int:
        cleaned_status = bonus.status.strip() if bonus.status else "pending"
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO bonus_records (session_id, student_name, b_point, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    bonus.session_id,
                    bonus.student_name.strip(),
                    float(bonus.b_point),
                    cleaned_status,
                ),
            )
            return int(cursor.lastrowid)

    def list_bonus_for_session(self, session_id: int, limit: int = 20) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, student_name, b_point, status
                  FROM bonus_records
                 WHERE session_id = ?
              ORDER BY id DESC
                 LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def create_session_template(
        self,
        campus_name: str,
        weekday_index: int,
        room_code: str,
        start_hour: int,
        end_hour: int,
    ) -> int:
        with self._database.connect() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO session_templates (
                        campus_name, weekday_index, room_code, start_hour, end_hour
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        campus_name.strip(),
                        weekday_index,
                        room_code.strip(),
                        start_hour,
                        end_hour,
                    ),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    """
                    SELECT id FROM session_templates
                     WHERE campus_name = ?
                       AND weekday_index = ?
                       AND room_code = ?
                       AND start_hour = ?
                       AND end_hour = ?
                    """,
                    (
                        campus_name.strip(),
                        weekday_index,
                        room_code.strip(),
                        start_hour,
                        end_hour,
                    ),
                ).fetchone()
                return int(row["id"]) if row else 0
            return int(cursor.lastrowid)

    def get_session_template(self, template_id: int) -> SessionTemplate | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, campus_name, weekday_index, room_code, start_hour, end_hour
                  FROM session_templates
                 WHERE id = ?
                """,
                (template_id,),
            ).fetchone()

        if not row:
            return None

        return SessionTemplate(
            id=int(row["id"]),
            campus_name=row["campus_name"],
            weekday_index=int(row["weekday_index"]),
            room_code=row["room_code"],
            start_hour=int(row["start_hour"]),
            end_hour=int(row["end_hour"]),
        )
