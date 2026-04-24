from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def parse_hhmm(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.strip().split(":", maxsplit=1)
    hour = int(hour_text)
    minute = int(minute_text)
    if not 0 <= hour <= 23:
        raise ValueError(f"Hour must be between 0 and 23: {value}")
    if not 0 <= minute <= 59:
        raise ValueError(f"Minute must be between 0 and 59: {value}")
    return hour, minute


def is_publish_window_open(
    timezone_name: str,
    publish_window: str,
    *,
    window_minutes: int = 15,
    reference_time: datetime | None = None,
) -> bool:
    local_now = reference_time or now_in_timezone(timezone_name)
    hour, minute = parse_hhmm(publish_window)
    window_start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    minutes_since_window_start = (local_now - window_start).total_seconds() / 60
    return 0 <= minutes_since_window_start <= window_minutes


def current_cycle_key(timezone_name: str) -> str:
    local_now = now_in_timezone(timezone_name)
    return local_now.date().isoformat()


def should_run_every_n_days(timezone_name: str, every_n_days: int, anchor_date: date = date(2026, 4, 23)) -> bool:
    local_today = now_in_timezone(timezone_name).date()
    return (local_today - anchor_date).days % every_n_days == 0


def week_key(timezone_name: str) -> str:
    local_today = now_in_timezone(timezone_name).date()
    year, week_number, _ = local_today.isocalendar()
    return f"{year}-W{week_number:02d}"


def iso_utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
