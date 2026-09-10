from datetime import datetime, time

import pytest

from alarm_clock.exceptions import AlarmNotFoundError, StorageCorruptionError
from alarm_clock.models import Alarm, DaysOfWeekSchedule, ScheduleKind
from alarm_clock.repository.json_file import JSONFileAlarmRepository


def make_alarm(alarm_id="1", **overrides):
    defaults = dict(
        id=alarm_id,
        schedule=DaysOfWeekSchedule(kind=ScheduleKind.DAILY, time_of_day=time(9, 0)),
        created_at=datetime.now(),
    )
    defaults.update(overrides)
    return Alarm(**defaults)


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "nested" / "alarms.json"


def test_creates_parent_directory_on_first_write(store_path):
    assert not store_path.parent.exists()
    repo = JSONFileAlarmRepository(store_path)
    repo.add(make_alarm())
    assert store_path.exists()


def test_missing_file_reads_as_empty(store_path):
    repo = JSONFileAlarmRepository(store_path)
    assert repo.list() == []


def test_round_trips_through_a_fresh_repository_instance(store_path):
    JSONFileAlarmRepository(store_path).add(make_alarm(label="Wake up"))
    reloaded = JSONFileAlarmRepository(store_path).get("1")
    assert reloaded.label == "Wake up"


def test_crud_cycle(store_path):
    repo = JSONFileAlarmRepository(store_path)
    repo.add(make_alarm("1"))
    repo.add(make_alarm("2"))
    assert {a.id for a in repo.list()} == {"1", "2"}

    repo.update(make_alarm("1", label="updated"))
    assert repo.get("1").label == "updated"

    repo.delete("2")
    assert {a.id for a in repo.list()} == {"1"}

    with pytest.raises(AlarmNotFoundError):
        repo.get("2")
    with pytest.raises(AlarmNotFoundError):
        repo.update(make_alarm("2"))
    with pytest.raises(AlarmNotFoundError):
        repo.delete("2")


def test_write_is_atomic_no_tmp_file_left_behind(store_path):
    repo = JSONFileAlarmRepository(store_path)
    repo.add(make_alarm())
    leftover_tmp_files = list(store_path.parent.glob(".alarms-*.tmp"))
    assert leftover_tmp_files == []


def test_corrupt_json_raises_storage_corruption_error(store_path):
    store_path.parent.mkdir(parents=True)
    store_path.write_text("{not valid json")
    repo = JSONFileAlarmRepository(store_path)
    with pytest.raises(StorageCorruptionError):
        repo.list()


def test_valid_json_wrong_shape_raises_storage_corruption_error(store_path):
    store_path.parent.mkdir(parents=True)
    store_path.write_text('[{"id": "1"}]')  # missing required fields
    repo = JSONFileAlarmRepository(store_path)
    with pytest.raises(StorageCorruptionError):
        repo.list()


def test_two_repository_instances_see_each_others_writes(store_path):
    repo_a = JSONFileAlarmRepository(store_path)
    repo_b = JSONFileAlarmRepository(store_path)
    repo_a.add(make_alarm("1"))
    assert repo_b.get("1").id == "1"
    repo_b.delete("1")
    assert repo_a.list() == []
