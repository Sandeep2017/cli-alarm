"""Strategy pattern for computing an alarm's next fire time.

Every strategy is a pure function of its schedule's own data plus a
reference time (`after`) — nothing here reads or writes mutable "last fired"
state, so the repository layer never needs to persist it (see PLAN.md §2/§6).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from alarm_clock.models import (
    Alarm,
    DaysOfWeekSchedule,
    IntervalSchedule,
    OnceSchedule,
    Schedule,
    ScheduleKind,
)

WEEKDAYS_BY_KIND: dict[ScheduleKind, frozenset[int]] = {
    ScheduleKind.DAILY: frozenset(range(7)),      # Mon..Sun
    ScheduleKind.WEEKDAYS: frozenset(range(5)),   # Mon..Fri
    ScheduleKind.WEEKENDS: frozenset({5, 6}),      # Sat, Sun
}


class AlarmStrategy(Protocol):
    def next_trigger(self, after: datetime) -> datetime | None:
        """First fire time strictly after `after`, or None if this alarm
        will never fire again."""
        ...


class DaysOfWeekStrategy:
    def __init__(self, schedule: DaysOfWeekSchedule):
        self.schedule = schedule
        self.weekdays = WEEKDAYS_BY_KIND[schedule.kind]

    def next_trigger(self, after: datetime) -> datetime | None:
        time_of_day = self.schedule.time_of_day
        # Try today first, then walk forward up to 6 more days.
        for day_offset in range(7):
            candidate_date = (after + timedelta(days=day_offset)).date()
            if candidate_date.weekday() not in self.weekdays:
                continue
            candidate = datetime.combine(candidate_date, time_of_day)
            if candidate > after:
                return candidate
        # Unreachable in practice (weekdays is always non-empty), but keep
        # the contract of returning None rather than raising.
        return None


class OnceStrategy:
    def __init__(self, schedule: OnceSchedule):
        self.schedule = schedule

    def next_trigger(self, after: datetime) -> datetime | None:
        return self.schedule.fire_at if self.schedule.fire_at > after else None


class IntervalStrategy:
    def __init__(self, schedule: IntervalSchedule):
        self.schedule = schedule

    def next_trigger(self, after: datetime) -> datetime | None:
        anchor, every = self.schedule.anchor, self.schedule.every
        if after < anchor:
            return anchor
        elapsed_steps = (after - anchor) // every
        return anchor + (elapsed_steps + 1) * every


STRATEGIES: dict[ScheduleKind, type] = {
    ScheduleKind.DAILY: DaysOfWeekStrategy,
    ScheduleKind.WEEKDAYS: DaysOfWeekStrategy,
    ScheduleKind.WEEKENDS: DaysOfWeekStrategy,
    ScheduleKind.ONCE: OnceStrategy,
    ScheduleKind.INTERVAL: IntervalStrategy,
}


def strategy_for(schedule: Schedule) -> AlarmStrategy:
    return STRATEGIES[schedule.kind](schedule)


def next_trigger_for(alarm: Alarm, after: datetime) -> datetime | None:
    """Next fire time for `alarm` strictly after `after`, or None if it
    won't fire again (including: it's disabled)."""
    if not alarm.enabled:
        return None
    return strategy_for(alarm.schedule).next_trigger(after)
