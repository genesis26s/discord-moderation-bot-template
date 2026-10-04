"""Generic helpers."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

_DURATION_RE = re.compile(r"(\d+)\s*([smhdw])", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> Optional[timedelta]:
    """Parse '1h30m', '10s', '2d' into timedelta. Returns None if invalid."""
    if not text:
        return None
    total = 0
    found = False
    for match in _DURATION_RE.finditer(text):
        found = True
        amount = int(match.group(1))
        unit = match.group(2).lower()
        total += amount * _UNIT_SECONDS[unit]
    if not found or total <= 0:
        return None
    return timedelta(seconds=total)


def humanize_timedelta(td: timedelta) -> str:
    secs = int(td.total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins, secs = divmod(secs, 60)
    if mins < 60:
        return f"{mins}m {secs}s" if secs else f"{mins}m"
    hrs, mins = divmod(mins, 60)
    if hrs < 24:
        return f"{hrs}h {mins}m" if mins else f"{hrs}h"
    days, hrs = divmod(hrs, 24)
    return f"{days}d {hrs}h" if hrs else f"{days}d"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ts(dt: datetime) -> int:
    return int(dt.timestamp())


def chunk(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]
