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

    bonus_record = BonusRecord(session_id=session_id, student_name="Bonus Student", b_point=5, status="awarded")
    bonus_id = service.record_bonus(bonus_record)

    with database.connect() as connection:
        row = connection.execute(
            "SELECT session_id, student_name, b_point, status FROM bonus_records WHERE id = ?",
            (bonus_id,),
        ).fetchone()

    assert row["session_id"] == session_id
    assert row["student_name"] == "Bonus Student"
    assert row["b_point"] == 5
    assert row["status"] == "awarded"

def test_list_sessions_and_updates(tmp_path):
    db_path = tmp_path / "attendance.db"
    database = Database(db_path)
    service = AttendanceService(database)
    service.initialize()

    monday_session = AttendanceSession(
        chapter_code="CS105",
        week_number=3,
        weekday_index=1,
        start_hour=8,
        end_hour=10,
        campus_name="Lappeenranta",
        room_code="C301",
    )
    tuesday_session = AttendanceSession(
        chapter_code="CS105",
        week_number=3,
        weekday_index=2,
        start_hour=12,
        end_hour=14,
        campus_name="Lappeenranta",
        room_code="C301",
    )

    monday_id = service.start_session(monday_session)
    tuesday_id = service.start_session(tuesday_session)

    alice = Student(student_code="1001", first_name="Alice", last_name="Example")
    bob = Student(student_code="1002", first_name="Bob", last_name="Example")

    alice_record_id = service.record_attendance(monday_id, alice)
    service.record_attendance(tuesday_id, bob)

    service.record_bonus(BonusRecord(session_id=monday_id, student_name="Alice Example", b_point=2, status="confirmed"))

    # Promote Alice's attendance to confirmed with bonus applied
    service.update_attendance_records(
        session_id=monday_id,
        updates=[
            {
                "id": alice_record_id,
                "status": "confirmed",
                "a_point": 5,
                "b_point": 2,
            }
        ],
    )

    sessions = service.list_sessions()
    assert len(sessions) == 2

    monday_summary = next(item for item in sessions if item["id"] == monday_id)
    assert monday_summary["attendance_count"] == 1
    assert monday_summary["attendance_confirmed_count"] == 1
    assert monday_summary["graded_count"] == 0
    assert monday_summary["bonus_count"] == 1
    assert monday_summary["bonus_confirmed_count"] == 1

    filtered = service.list_sessions(weekday_index=1)
    assert len(filtered) == 1
    assert filtered[0]["id"] == monday_id

    attendance_rows = service.get_session_attendance(monday_id)
    assert len(attendance_rows) == 1
    assert attendance_rows[0]["status"] == "confirmed"
    assert attendance_rows[0]["b_point"] == 2

    bonus_summary = service.get_session_bonus_summary(monday_id)
    assert len(bonus_summary) == 1
    assert bonus_summary[0]["record_count"] == 1
    assert bonus_summary[0]["confirmed_count"] == 1
    assert bonus_summary[0]["total_bonus"] == 2

def test_update_bonus_status_for_session(tmp_path):
    db_path = tmp_path / "attendance.db"
    database = Database(db_path)
    service = AttendanceService(database)
    service.initialize()

    session = AttendanceSession(
        chapter_code="CS200",
        week_number=4,
        weekday_index=3,
        start_hour=14,
        end_hour=16,
        campus_name="Lahti",
        room_code="D101",
    )
    session_id = service.start_session(session)

    bonus_pending_id = service.record_bonus(
    BonusRecord(session_id=session_id, student_name="Charlie Example", b_point=1, status="pending")
    )

    service.update_bonus_status_for_session(
        session_id=session_id,
        record_ids=[bonus_pending_id],
        status="confirmed",
    )

    bonus_rows = service.list_bonus_for_session(session_id, limit=None)
    assert len(bonus_rows) == 1
    assert bonus_rows[0]["status"] == "confirmed"
