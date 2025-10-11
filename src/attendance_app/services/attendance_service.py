from __future__ import annotations

import sqlite3

from typing import Iterable

from attendance_app.data import Database
from attendance_app.models import AttendanceSession, BonusRecord, SessionTemplate, Student
from attendance_app.config.settings import settings, user_settings_store

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
                  AND weekday_index = ?
                  AND start_hour = ?
                  AND end_hour = ?
                  AND campus_name = ?
                  AND room_code = ?
                """,
                (
                    session.chapter_code.strip(),
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
                    chapter_code, weekday_index, start_hour, end_hour,
                    campus_name, room_code
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.chapter_code.strip(),
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
        a_point: int | None = None,
        b_point: int | None = None,
        t_point: int | None = None,
        status: str = "recorded",
    ) -> int:
        student_identifier = student.student_code.strip()
        student_name = student.display_name if student.display_name != student.student_code else None
        default_attendance = int(
            user_settings_store.get("default_attendance_points", settings.default_attendance_points)
        )
        default_bonus = int(user_settings_store.get("default_bonus_points", settings.default_bonus_points))

        a_value = int(a_point) if a_point is not None else default_attendance
        if b_point is not None:
            b_value = int(b_point)
        else:
            b_value = default_bonus if source == "bonus" else 0
        total_value = int(t_point) if t_point is not None else a_value + b_value
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

    def list_sessions(
        self,
        *,
        weekday_index: int | None = None,
        start_hour: int | None = None,
        end_hour: int | None = None,
    ) -> list[dict]:
        query_parts = [
            "SELECT",
            "    s.id,",
            "    s.chapter_code,",
            "    s.weekday_index,",
            "    s.start_hour,",
            "    s.end_hour,",
            "    s.campus_name,",
            "    s.room_code,",
            "    s.created_at,",
            "    s.status,",
            "    COALESCE((SELECT COUNT(*) FROM attendance_records ar WHERE ar.session_id = s.id), 0) AS attendance_count,",
            "    COALESCE((SELECT SUM(CASE WHEN ar.status = 'confirmed' THEN 1 ELSE 0 END) FROM attendance_records ar WHERE ar.session_id = s.id), 0) AS attendance_confirmed_count,",
            "    COALESCE((SELECT SUM(CASE WHEN ar.status = 'graded' THEN 1 ELSE 0 END) FROM attendance_records ar WHERE ar.session_id = s.id), 0) AS graded_count,",
            "    COALESCE((SELECT COUNT(*) FROM bonus_records br WHERE br.session_id = s.id), 0) AS bonus_count,",
            "    COALESCE((SELECT SUM(CASE WHEN br.status = 'confirmed' THEN 1 ELSE 0 END) FROM bonus_records br WHERE br.session_id = s.id), 0) AS bonus_confirmed_count",
            "FROM attendance_sessions AS s",
        ]

        params: list[int] = []
        conditions: list[str] = []

        if weekday_index is not None:
            conditions.append("s.weekday_index = ?")
            params.append(weekday_index)

        if start_hour is not None and end_hour is not None:
            conditions.append("s.start_hour = ? AND s.end_hour = ?")
            params.extend([start_hour, end_hour])

        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))

        query_parts.append("ORDER BY datetime(s.created_at) DESC, s.id DESC")

        sql = "\n".join(query_parts)

        with self._database.connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()

        return [dict(row) for row in rows]

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
          SELECT id, chapter_code, weekday_index,
                       start_hour, end_hour, campus_name, room_code, created_at
                  FROM attendance_sessions
              ORDER BY created_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_session_attendance(self, session_id: int) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id,
                       student_id,
                       student_name,
                       source,
                       a_point,
                       b_point,
                       t_point,
                       status,
                       recorded_at
                  FROM attendance_records
                 WHERE session_id = ?
              ORDER BY LOWER(COALESCE(student_name, student_id)) ASC,
                       student_id ASC
                """,
                (session_id,),
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
                    int(bonus.b_point),
                    cleaned_status,
                ),
            )
            return int(cursor.lastrowid)

    def list_bonus_for_session(self, session_id: int, limit: int | None = 20) -> list[dict]:
        query = [
            "SELECT id, student_name, b_point, status",
            "  FROM bonus_records",
            " WHERE session_id = ?",
            " ORDER BY id DESC",
        ]

        params: list[int | None] = [session_id]
        if limit is not None:
            query.append(" LIMIT ?")
            params.append(limit)

        sql = "".join(query)

        with self._database.connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()

        return [dict(row) for row in rows]

    def get_session_bonus_summary(self, session_id: int) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                                SELECT COALESCE(student_name, '') AS student_name,
                                             SUM(b_point) AS total_bonus,
                                             SUM(CASE WHEN status = 'confirmed' THEN b_point ELSE 0 END) AS confirmed_bonus,
                                             COUNT(*) AS record_count,
                                             SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed_count
                  FROM bonus_records
                 WHERE session_id = ?
                            GROUP BY COALESCE(student_name, '')
                            ORDER BY LOWER(COALESCE(student_name, ''))
                """,
                (session_id,),
            ).fetchall()
            summary: list[dict] = []
            for row in rows:
                summary.append(
                    {
                        "student_name": row["student_name"],
                        "total_bonus": int(row["total_bonus"] or 0),
                        "confirmed_bonus": int(row["confirmed_bonus"] or 0),
                        "record_count": int(row["record_count"] or 0),
                        "confirmed_count": int(row["confirmed_count"] or 0),
                    }
                )
            return summary

    def update_attendance_records(
        self,
        *,
        session_id: int,
        updates: Iterable[dict],
    ) -> None:
        payloads = list(updates)
        if not payloads:
            return

        with self._database.connect() as connection:
            for payload in payloads:
                record_id = int(payload["id"])
                status = str(payload.get("status", "recorded") or "recorded").strip()
                a_point = int(payload.get("a_point", 0) or 0)
                b_point = int(payload.get("b_point", 0) or 0)
                t_point_raw = payload.get("t_point")
                t_point = int(t_point_raw) if t_point_raw is not None else a_point + b_point
                student_name = payload.get("student_name")

                connection.execute(
                    """
                    UPDATE attendance_records
                       SET status = ?,
                           a_point = ?,
                           b_point = ?,
                           t_point = ?,
                           student_name = COALESCE(?, student_name)
                     WHERE id = ?
                       AND session_id = ?
                    """,
                    (
                        status,
                        a_point,
                        b_point,
                        t_point,
                        student_name,
                        record_id,
                        session_id,
                    ),
                )

    def update_status_for_attendance_records(
        self,
        *,
        session_id: int,
        record_ids: Iterable[int],
        status: str,
    ) -> None:
        ids = [int(rid) for rid in record_ids]
        if not ids:
            return

        placeholders = ", ".join(["?"] * len(ids))
        query = (
            "UPDATE attendance_records SET status = ? WHERE session_id = ? AND id IN ("
            + placeholders
            + ")"
        )

        with self._database.connect() as connection:
            connection.execute(query, (status.strip(), session_id, *ids))

    def update_bonus_status_for_session(
        self,
        *,
        session_id: int,
        record_ids: Iterable[int],
        status: str,
    ) -> None:
        ids = [int(rid) for rid in record_ids]
        if not ids:
            return

        placeholders = ", ".join(["?"] * len(ids))
        query = (
            "UPDATE bonus_records SET status = ? WHERE session_id = ? AND id IN ("
            + placeholders
            + ")"
        )

        with self._database.connect() as connection:
            connection.execute(query, (status.strip(), session_id, *ids))

    def update_session_status(self, session_id: int, status: str) -> None:
        cleaned_status = status.strip() if status else "draft"
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE attendance_sessions SET status = ? WHERE id = ?",
                (cleaned_status, session_id),
            )

    def confirm_attendance_for_session(self, session_id: int) -> bool:
        """Mark all attendance records as confirmed and update session if applicable.

        Returns True when the parent session status was updated to confirmed.
        """
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE attendance_records SET status = 'confirmed' WHERE session_id = ?",
                (session_id,),
            )

            total = connection.execute(
                "SELECT COUNT(*) FROM attendance_records WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]

            remaining = connection.execute(
                """
                SELECT COUNT(*)
                  FROM attendance_records
                 WHERE session_id = ?
                   AND status <> 'confirmed'
                """,
                (session_id,),
            ).fetchone()[0]

            if int(total or 0) > 0 and int(remaining or 0) == 0:
                connection.execute(
                    "UPDATE attendance_sessions SET status = 'confirmed' WHERE id = ?",
                    (session_id,),
                )
                return True

        return False

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
