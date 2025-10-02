from __future__ import annotations

from datetime import datetime

WEEKDAY_OPTIONS: tuple[tuple[str, int], ...] = (
    ("Monday", 1),
    ("Tuesday", 2),
    ("Wednesday", 3),
    ("Thursday", 4),
    ("Friday", 5),
)


class InvalidHourRange(ValueError):
    pass


def parse_hour_range(start: str, end: str) -> tuple[int, int]:
    try:
        start_hour = int(start)
        end_hour = int(end)
    except ValueError as exc:
        raise InvalidHourRange("Hour values must be integers.") from exc

    if not (0 <= start_hour <= 23 and 1 <= end_hour <= 24):
        raise InvalidHourRange("Hours must be between 00-23 for start and 01-24 for end.")

    if start_hour >= end_hour:
        raise InvalidHourRange("End hour must be later than start hour.")

    return start_hour, end_hour


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        candidate = value.strip().replace(" ", "T", 1)
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue

    raise ValueError(f"Unsupported datetime value: {value!r}")


def format_relative_time(value: datetime | str, *, now: datetime | None = None) -> str:
    reference = now or datetime.utcnow()
    moment = _coerce_datetime(value)

    delta = reference - moment
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return "just now"

    if total_seconds < 60:
        return "just now"

    minutes = total_seconds // 60
    if minutes == 1:
        return "1 minute ago"
    if minutes < 60:
        return f"{minutes} minutes ago"

    hours = minutes // 60
    if hours == 1:
        return "1 hour ago"
    if hours < 24:
        return f"{hours} hours ago"

    days = hours // 24
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"

    weeks = days // 7
    if weeks == 1:
        return "1 week ago"
    if weeks < 5:
        return f"{weeks} weeks ago"

    months = days // 30
    if months == 1:
        return "1 month ago"
    if months < 12:
        return f"{months} months ago"

    years = days // 365
    if years == 1:
        return "1 year ago"
    return f"{years} years ago"
