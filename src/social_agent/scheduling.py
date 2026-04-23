from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


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

