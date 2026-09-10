from datetime import datetime, time, timedelta

import pytest

from alarm_clock.models import Alarm, DaysOfWeekSchedule, IntervalSchedule, OnceSchedule, ScheduleKind
from alarm_clock.strategies import next_trigger_for, strategy_for

THURSDAY = datetime(2026, 9, 10, 10, 0)  # 2026-09-10 is a Thursday


def test_daily_rolls_to_tomorrow_when_todays_slot_passed():
    schedule = DaysOfWeekSchedule(kind=ScheduleKind.DAILY, time_of_day=time(9, 0))
    assert strategy_for(schedule).next_trigger(THURSDAY) == datetime(2026, 9, 11, 9, 0)


def test_daily_stays_today_when_slot_is_later():
    schedule = DaysOfWeekSchedule(kind=ScheduleKind.DAILY, time_of_day=time(15, 0))
    assert strategy_for(schedule).next_trigger(THURSDAY) == datetime(2026, 9, 10, 15, 0)


def test_weekdays_skips_weekend():
    # Friday 2026-09-11, after its own slot -> next Monday 2026-09-14
    friday_evening = datetime(2026, 9, 11, 20, 0)
    schedule = DaysOfWeekSchedule(kind=ScheduleKind.WEEKDAYS, time_of_day=time(9, 0))
    assert strategy_for(schedule).next_trigger(friday_evening) == datetime(2026, 9, 14, 9, 0)


def test_weekends_from_thursday_jumps_to_saturday():
    schedule = DaysOfWeekSchedule(kind=ScheduleKind.WEEKENDS, time_of_day=time(9, 0))
    assert strategy_for(schedule).next_trigger(THURSDAY) == datetime(2026, 9, 12, 9, 0)


def test_once_future_returns_fire_at():
    fire_at = THURSDAY + timedelta(minutes=5)
    schedule = OnceSchedule(fire_at=fire_at)
    assert strategy_for(schedule).next_trigger(THURSDAY) == fire_at


def test_once_past_returns_none():
    schedule = OnceSchedule(fire_at=THURSDAY - timedelta(minutes=5))
    assert strategy_for(schedule).next_trigger(THURSDAY) is None


def test_interval_before_anchor_returns_anchor():
    anchor = THURSDAY + timedelta(minutes=10)
    schedule = IntervalSchedule(every=timedelta(minutes=5), anchor=anchor)
    assert strategy_for(schedule).next_trigger(THURSDAY) == anchor


def test_interval_returns_next_boundary_after_anchor():
    anchor = THURSDAY - timedelta(minutes=3)
    schedule = IntervalSchedule(every=timedelta(minutes=10), anchor=anchor)
    assert strategy_for(schedule).next_trigger(THURSDAY) == anchor + timedelta(minutes=10)


def test_interval_exactly_on_boundary_returns_next_one_strictly_after():
    anchor = THURSDAY
    schedule = IntervalSchedule(every=timedelta(minutes=10), anchor=anchor)
    boundary = anchor + timedelta(minutes=10)
    assert strategy_for(schedule).next_trigger(boundary) == boundary + timedelta(minutes=10)


def test_next_trigger_for_disabled_alarm_is_none():
    alarm = Alarm(
        id="1",
        schedule=OnceSchedule(fire_at=THURSDAY + timedelta(minutes=5)),
        enabled=False,
        created_at=THURSDAY,
    )
    assert next_trigger_for(alarm, THURSDAY) is None
