import pytest

from attendance_app.data import Database
from attendance_app.models import AttendanceSession, BonusRecord, Student
from attendance_app.services import AttendanceService, DuplicateAttendanceError


def test_record_attendance_prevents_duplicates(tmp_path):
    db_path = tmp_path / "attendance.db"
    database = Database(db_path)
    service = AttendanceService(database)
    service.initialize()

    session = AttendanceSession(
        chapter_code="CS101",
        week_number=1,
        weekday_index=1,
        start_hour=10,
        end_hour=12,
        campus_name="Lappeenranta",
        room_code="A101",
    )
    session_id = service.start_session(session)

    student = Student(student_code="123456", first_name="Test", last_name="Student")

    first_record_id = service.record_attendance(session_id, student)
    assert first_record_id > 0

    with database.connect() as connection:
        row = connection.execute(
            "SELECT a_point, b_point, t_point, status FROM attendance_records WHERE id = ?",
            (first_record_id,),
        ).fetchone()

    assert row["a_point"] == 5
    assert row["b_point"] == 0
    assert row["t_point"] == 5
    assert row["status"] == "recorded"

    with pytest.raises(DuplicateAttendanceError):
        service.record_attendance(session_id, student)


def test_record_bonus_points(tmp_path):
    db_path = tmp_path / "attendance.db"
    database = Database(db_path)
    service = AttendanceService(database)
    service.initialize()

    session = AttendanceSession(
        chapter_code="CS102",
        week_number=2,
        weekday_index=2,
        start_hour=12,
        end_hour=14,
        campus_name="Lappeenranta",
        room_code="B201",
    )
    session_id = service.start_session(session)

    bonus_record = BonusRecord(session_id=session_id, student_name="Bonus Student", b_point=5.0, status="awarded")
    bonus_id = service.record_bonus(bonus_record)

    with database.connect() as connection:
        row = connection.execute(
            "SELECT session_id, student_name, b_point, status FROM bonus_records WHERE id = ?",
            (bonus_id,),
        ).fetchone()

    assert row["session_id"] == session_id
    assert row["student_name"] == "Bonus Student"
    assert row["b_point"] == 5.0
    assert row["status"] == "awarded"
