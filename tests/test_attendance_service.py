import pytest

from attendance_app.data import Database
from attendance_app.models import AttendanceSession, Student
from attendance_app.services import AttendanceService, DuplicateAttendanceError


def test_record_attendance_prevents_duplicates(tmp_path):
    db_path = tmp_path / "attendance.db"
    service = AttendanceService(Database(db_path))
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

    with pytest.raises(DuplicateAttendanceError):
        service.record_attendance(session_id, student)
