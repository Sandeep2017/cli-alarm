from datetime import datetime, time, timedelta

import pytest
from freezegun import freeze_time

from alarm_clock.models import DaysOfWeekSchedule, IntervalSchedule, OnceSchedule, ScheduleKind
from alarm_clock.scheduler import _tick
from alarm_clock.service import AlarmClock


@pytest.fixture
def clock():
    return AlarmClock()


def test_tick_rings_daily_alarm_once_its_slot_is_crossed_but_not_again(clock, capsys):
    with freeze_time("2026-09-10 08:59:00"):
        clock.create_alarm(schedule=DaysOfWeekSchedule(kind=ScheduleKind.DAILY, time_of_day=time(9, 0)))
        since = datetime.now()

    with freeze_time("2026-09-10 09:00:01"):
        since = _tick(clock, since=since)
    assert capsys.readouterr().out.count("\N{ALARM CLOCK}") == 1

    with freeze_time("2026-09-10 09:00:02"):
        _tick(clock, since=since)
    assert capsys.readouterr().out == ""


def test_tick_disables_once_alarm_after_ringing(clock, capsys):
    now = datetime.now()
    alarm = clock.create_alarm(schedule=OnceSchedule(fire_at=now - timedelta(seconds=1)))
    _tick(clock, since=now - timedelta(minutes=1))
    assert clock.get_alarm(alarm.id).enabled is False
    assert "\N{ALARM CLOCK}" in capsys.readouterr().out


def test_tick_rings_multiple_missed_interval_boundaries_in_one_gap(clock, capsys):
    now = datetime.now()
    clock.create_alarm(
        schedule=IntervalSchedule(every=timedelta(seconds=1), anchor=now - timedelta(seconds=10))
    )
    _tick(clock, since=now - timedelta(seconds=5))
    out = capsys.readouterr().out
    # ~5 one-second boundaries should have been crossed in that 5s gap.
    assert out.count("\N{ALARM CLOCK}") >= 4


def test_tick_does_not_ring_disabled_alarms(clock, capsys):
    alarm = clock.create_alarm(schedule=OnceSchedule(fire_at=datetime.now() - timedelta(seconds=1)))
    clock.set_enabled(alarm.id, enabled=False)
    _tick(clock, since=datetime.now() - timedelta(minutes=1))
    assert capsys.readouterr().out == ""
