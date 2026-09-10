from datetime import datetime, time

import pytest

from alarm_clock.exceptions import AlarmNotFoundError
from alarm_clock.models import Alarm, DaysOfWeekSchedule, ScheduleKind
from alarm_clock.repository.memory import InMemoryAlarmRepository


def make_alarm(alarm_id="1", **overrides):
    defaults = dict(
        id=alarm_id,
        schedule=DaysOfWeekSchedule(kind=ScheduleKind.DAILY, time_of_day=time(9, 0)),
        created_at=datetime.now(),
    )
    defaults.update(overrides)
    return Alarm(**defaults)


def test_add_and_get():
    repo = InMemoryAlarmRepository()
    alarm = make_alarm()
    repo.add(alarm)
    assert repo.get("1") == alarm


def test_get_missing_raises():
    repo = InMemoryAlarmRepository()
    with pytest.raises(AlarmNotFoundError):
        repo.get("missing")


def test_list_returns_all():
    repo = InMemoryAlarmRepository()
    repo.add(make_alarm("1"))
    repo.add(make_alarm("2"))
    assert {a.id for a in repo.list()} == {"1", "2"}


def test_update_replaces_existing():
    repo = InMemoryAlarmRepository()
    repo.add(make_alarm("1", label="old"))
    repo.update(make_alarm("1", label="new"))
    assert repo.get("1").label == "new"


def test_update_missing_raises():
    repo = InMemoryAlarmRepository()
    with pytest.raises(AlarmNotFoundError):
        repo.update(make_alarm("missing"))


def test_delete_removes_and_missing_raises():
    repo = InMemoryAlarmRepository()
    repo.add(make_alarm("1"))
    repo.delete("1")
    with pytest.raises(AlarmNotFoundError):
        repo.get("1")
    with pytest.raises(AlarmNotFoundError):
        repo.delete("1")
