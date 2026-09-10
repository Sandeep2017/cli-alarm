"""Parsing of human-entered time-of-day and duration strings.

Pure functions with no CLI/click dependency, so a future API layer accepting
the same human strings (rather than structured JSON) can reuse them.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from alarm_clock.exceptions import InvalidTimeFormatError

_TIME_FORMATS = (
    "%H:%M",     # 13:30
    "%I:%M%p",   # 1:30PM
    "%I:%M %p",  # 1:30 PM
)

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smh])\s*$", re.IGNORECASE)
_DURATION_UNITS = {"s": "seconds", "m": "minutes", "h": "hours"}


def parse_time_of_day(text: str) -> time:
    """Parse "13:30" (24h) or "1:30pm" / "1:30 PM" (12h) into a `time`."""
    candidate = text.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).time()
        except ValueError:
            continue
    raise InvalidTimeFormatError(
        f"Could not parse {text!r} as a time of day. "
        "Expected formats like '13:30', '1:30pm', or '1:30 PM'."
    )


def parse_duration(text: str) -> timedelta:
    """Parse "5m", "10s", "1h" (int + s/m/h unit) into a `timedelta`."""
    match = _DURATION_RE.match(text)
    if not match:
        raise InvalidTimeFormatError(
            f"Could not parse {text!r} as a duration. "
            "Expected formats like '5m', '30s', or '1h'."
        )
    amount, unit = match.groups()
    kwargs = {_DURATION_UNITS[unit.lower()]: int(amount)}
    duration = timedelta(**kwargs)
    if duration <= timedelta(0):
        raise InvalidTimeFormatError("Duration must be greater than zero.")
    return duration
