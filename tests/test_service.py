from datetime import datetime, time, timedelta

import pytest

from alarm_clock.exceptions import AlarmNotFoundError, InvalidAlarmError
from alarm_clock.models import DaysOfWeekSchedule, ScheduleKind
from alarm_clock.service import AlarmClock


@pytest.fixture
def clock():
    return AlarmClock()


def daily_schedule(hour=9):
    return DaysOfWeekSchedule(kind=ScheduleKind.DAILY, time_of_day=time(hour, 0))


def test_create_alarm_assigns_id_and_defaults(clock):
    alarm = clock.create_alarm(schedule=daily_schedule(), label="Wake up")
    assert alarm.id
    assert alarm.label == "Wake up"
    assert alarm.enabled is True


def test_create_alarm_with_invalid_schedule_raises_invalid_alarm_error(clock):
    # A raw dict that fails Alarm's schedule validation once it reaches the
    # model constructor inside create_alarm (rather than a Schedule model,
    # which would already have rejected this at its own construction).
    bad_schedule = {"kind": "interval", "every": 0, "anchor": datetime.now().isoformat()}
    with pytest.raises(InvalidAlarmError):
        clock.create_alarm(schedule=bad_schedule)


def test_get_list_delete_roundtrip(clock):
    a1 = clock.create_alarm(schedule=daily_schedule())
    a2 = clock.create_alarm(schedule=daily_schedule(hour=10))
    assert {a.id for a in clock.list_alarms()} == {a1.id, a2.id}

    clock.delete_alarm(a1.id)
    assert {a.id for a in clock.list_alarms()} == {a2.id}
    with pytest.raises(AlarmNotFoundError):
        clock.get_alarm(a1.id)


def test_update_alarm_only_touches_given_fields(clock):
    alarm = clock.create_alarm(schedule=daily_schedule(), label="original")
    updated = clock.update_alarm(alarm.id, label="renamed")
    assert updated.label == "renamed"
    assert updated.schedule == alarm.schedule
    assert updated.enabled is True


def test_update_alarm_can_clear_label_to_none(clock):
    alarm = clock.create_alarm(schedule=daily_schedule(), label="original")
    updated = clock.update_alarm(alarm.id, label=None)
    assert updated.label is None


def test_set_enabled(clock):
    alarm = clock.create_alarm(schedule=daily_schedule())
    disabled = clock.set_enabled(alarm.id, enabled=False)
    assert disabled.enabled is False
    enabled = clock.set_enabled(alarm.id, enabled=True)
    assert enabled.enabled is True


def test_update_unknown_id_raises(clock):
    with pytest.raises(AlarmNotFoundError):
        clock.update_alarm("missing", label="x")


def test_delete_unknown_id_raises(clock):
    with pytest.raises(AlarmNotFoundError):
        clock.delete_alarm("missing")
