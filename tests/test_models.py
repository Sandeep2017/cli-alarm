from datetime import datetime, time, timedelta

import pytest
from pydantic import ValidationError

from alarm_clock.models import (
    Alarm,
    DaysOfWeekSchedule,
    IntervalSchedule,
    OnceSchedule,
    ScheduleKind,
)


def test_days_of_week_schedule_accepts_daily_weekdays_weekends():
    for kind in (ScheduleKind.DAILY, ScheduleKind.WEEKDAYS, ScheduleKind.WEEKENDS):
        schedule = DaysOfWeekSchedule(kind=kind, time_of_day=time(9, 0))
        assert schedule.kind == kind


def test_days_of_week_schedule_rejects_once():
    with pytest.raises(ValidationError):
        DaysOfWeekSchedule(kind=ScheduleKind.ONCE, time_of_day=time(9, 0))


def test_interval_schedule_rejects_non_positive_every():
    with pytest.raises(ValidationError):
        IntervalSchedule(every=timedelta(0), anchor=datetime.now())
    with pytest.raises(ValidationError):
        IntervalSchedule(every=timedelta(minutes=-5), anchor=datetime.now())


def test_alarm_schedule_is_discriminated_union():
    alarm = Alarm(
        id="abc",
        schedule=OnceSchedule(fire_at=datetime.now() + timedelta(minutes=5)),
        created_at=datetime.now(),
    )
    assert isinstance(alarm.schedule, OnceSchedule)


def test_alarm_round_trips_through_json():
    alarm = Alarm(
        id="abc",
        label="Wake up",
        schedule=DaysOfWeekSchedule(kind=ScheduleKind.WEEKDAYS, time_of_day=time(7, 0)),
        created_at=datetime.now(),
    )
    dumped = alarm.model_dump(mode="json")
    restored = Alarm.model_validate(dumped)
    assert restored == alarm


def test_alarm_schedule_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        Alarm(
            id="abc",
            schedule={"kind": "monthly", "time_of_day": "09:00"},
            created_at=datetime.now(),
        )
