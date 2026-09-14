"""Time parsing helpers shared by alarm front-ends."""

from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

_UNIT_TO_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)([smhd])")


_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def parse_alarm_time(token: str, now: Optional[_dt.datetime] = None) -> _dt.datetime:
    """Parse an absolute alarm time.

    Supported forms (case-insensitive):
      12-sept-2026 16:00
      12-sept-2026 16:00:00
      2026-09-12 16:00
      12/09/2026 16:00
      12-sep-2026 4pm
      16:00            (today, or tomorrow if already passed)

    Returns a naive local datetime.
    """
    now = now or _dt.datetime.now()
    raw = token.strip()
    if not raw:
        raise ValueError("empty alarm time")

    # Time-only form: "16:00" or "4pm"
    if _looks_like_time_only(raw):
        return _parse_time_only(raw, now)

    parts = raw.replace(",", " ").split()
    if len(parts) < 2:
        raise ValueError(f"could not parse alarm time: {token!r}")

    date_part, time_part = parts[0], parts[1]
    year, month, day = _parse_date(date_part)
    hour, minute, second = _parse_time(time_part)

    return _dt.datetime(year, month, day, hour, minute, second)


def parse_duration(token: str, now: Optional[_dt.datetime] = None) -> _dt.datetime:
    """Parse a relative duration like ``30m``, ``2h``, ``1d``, ``1h30m``, ``0.5m``.

    Returns an absolute datetime = now + duration. Accepts decimals (``0.5m``)
    and compound forms (``1h30m``). Raises ValueError with a helpful message
    otherwise.
    """
    now = now or _dt.datetime.now()
    token = token.strip().lower()
    if not token:
        raise ValueError("empty duration")

    matches = _DURATION_RE.findall(token)
    if not matches or "".join(m[0] + m[1] for m in matches) != token:
        raise ValueError(
            f"bad duration {token!r}: use <number><unit> like 30m, 2h, 1d, "
            f"1h30m, or 0.5m (units: s, m, h, d)"
        )

    total = 0.0
    for num, unit in matches:
        total += float(num) * _UNIT_TO_SECONDS[unit]
    if total <= 0:
        raise ValueError(f"duration must be positive: {token!r}")
    return now + _dt.timedelta(seconds=total)


def _looks_like_time_only(raw: str) -> bool:
    body = raw.lower().rstrip("z")
    return ("am" in body or "pm" in body or ":" in body) and not any(
        c in body for c in "/-."
    )


def _parse_time_only(raw: str, now: _dt.datetime) -> _dt.datetime:
    """Time-only form: today, or tomorrow if already passed."""
    hour, minute, second = _parse_time(raw)
    candidate = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if candidate <= now:
        candidate += _dt.timedelta(days=1)
    return candidate


def _parse_date(token: str) -> tuple[int, int, int]:
    token = token.strip().lower().rstrip(",")
    # 12-sept-2026 / 12-sep-2026
    if "-" in token and any(c.isalpha() for c in token):
        day_s, mon_s, year_s = token.split("-")
        return int(year_s), _month_name(mon_s), int(day_s)
    # 2026-09-12
    if token.count("-") == 2 and token[4] == "-":
        y, m, d = token.split("-")
        return int(y), int(m), int(d)
    # 12/09/2026
    if token.count("/") == 2:
        a, b, c = token.split("/")
        return int(c), int(b), int(a)
    raise ValueError(f"unrecognized date: {token!r}")


def _month_name(token: str) -> int:
    key = token.lower()
    if key in _MONTHS:
        return _MONTHS[key]
    raise ValueError(f"unknown month: {token!r}")


def _parse_time(token: str) -> tuple[int, int, int]:
    token = token.strip().lower()
    ampm = None
    for suffix in ("am", "pm"):
        if token.endswith(suffix):
            ampm = suffix
            token = token[: -len(suffix)]
            break
    if ":" in token:
        h, m, s = (token.split(":") + ["0"])[:3]
        hour, minute, second = int(h), int(m), int(s)
    else:
        hour = int(token)
        minute = second = 0
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23):
        raise ValueError(f"bad hour: {token!r}")
    if not (0 <= minute <= 59):
        raise ValueError(f"bad minute: {token!r}")
    if not (0 <= second <= 59):
        raise ValueError(f"bad second: {token!r}")
    return hour, minute, second