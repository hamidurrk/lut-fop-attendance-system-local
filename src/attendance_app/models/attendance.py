from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


WEEKDAY_LABELS = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
}


@dataclass(slots=True)
class Student:
    student_code: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None

    @property
    def display_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        name = " ".join(part for part in parts if part).strip()
        return name if name else self.student_code


@dataclass(slots=True)
class AttendanceSession:
    chapter_code: str
    week_number: int
    weekday_index: int
    start_hour: int
    end_hour: int
    campus_name: str
    room_code: str
    created_at: datetime = datetime.utcnow()

    def session_key(self) -> str:
        return (
            f"{self.chapter_code}-W{self.week_number:02d}-D{self.weekday_index}-"
            f"{self.start_hour:02d}-{self.end_hour:02d}-{self.campus_name}-{self.room_code}"
        )


@dataclass(slots=True)
class AttendanceRecord:
    session_id: int
    student_code: str
    student_name: Optional[str] = None
    recorded_at: datetime = field(default_factory=datetime.utcnow)
    source: str = "manual"
    payload: Optional[str] = None


@dataclass(slots=True)
class SessionTemplate:
    id: int
    campus_name: str
    weekday_index: int
    room_code: str
    start_hour: int
    end_hour: int

    def weekday_label(self) -> str:
        return WEEKDAY_LABELS.get(self.weekday_index, f"Day {self.weekday_index}")

    def display_label(self) -> str:
        return (
            f"{self.campus_name} · {self.room_code} · "
            f"{self.weekday_label()} {self.start_hour:02d}-{self.end_hour:02d}"
        )
