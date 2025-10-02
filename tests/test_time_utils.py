from datetime import datetime, timedelta

from attendance_app.utils import format_relative_time

def test_format_relative_time_minutes():
    now = datetime(2025, 10, 2, 12, 0, 0)
    timestamp = now - timedelta(minutes=30)
    assert format_relative_time(timestamp, now=now) == "30 minutes ago"


def test_format_relative_time_just_now():
    now = datetime(2025, 10, 2, 12, 0, 0)
    timestamp = now - timedelta(seconds=10)
    assert format_relative_time(timestamp, now=now) == "just now"
