import re

import pytest
from click.testing import CliRunner

from alarm_clock.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store(tmp_path):
    return tmp_path / "alarms.json"


def invoke(runner, store, *args):
    return runner.invoke(main, [*args, "--store", str(store)])


def _extract_id(create_output: str) -> str:
    match = re.search(r"Created alarm (\S+)", create_output)
    assert match, create_output
    return match.group(1)


def test_set_with_time_and_days_matches_readme_example(runner, store):
    result = invoke(runner, store, "set", "1:30pm", "--label", "Wake up", "--days", "weekdays")
    assert result.exit_code == 0, result.output
    assert "Created alarm" in result.output
    assert "Wake up" in result.output
    assert "weekdays at 13:30" in result.output


def test_set_with_in_creates_one_time_alarm(runner, store):
    result = invoke(runner, store, "set", "--in", "5m", "--label", "Tea")
    assert result.exit_code == 0, result.output
    assert "once at" in result.output


def test_set_with_every_creates_interval_alarm(runner, store):
    result = invoke(runner, store, "set", "--every", "10m", "--label", "Stretch")
    assert result.exit_code == 0, result.output
    assert "every 0:10:00" in result.output


def test_set_rejects_mixing_modes(runner, store):
    result = invoke(runner, store, "set", "1:30pm", "--days", "daily", "--in", "5m")
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_set_time_without_days_is_an_error(runner, store):
    result = invoke(runner, store, "set", "1:30pm")
    assert result.exit_code != 0


def test_set_with_no_arguments_is_an_error(runner, store):
    result = invoke(runner, store, "set")
    assert result.exit_code != 0


def test_set_rejects_bad_time_format(runner, store):
    result = invoke(runner, store, "set", "25:99", "--days", "daily")
    assert result.exit_code != 0
    assert "Could not parse" in result.output


def test_list_then_delete(runner, store):
    create = invoke(runner, store, "set", "9:00am", "--days", "daily", "--label", "Gym")
    alarm_id = _extract_id(create.output)

    listing = invoke(runner, store, "list")
    assert alarm_id in listing.output
    assert "Gym" in listing.output

    delete = invoke(runner, store, "delete", alarm_id)
    assert "Deleted alarm" in delete.output

    listing_after = invoke(runner, store, "list")
    assert "No alarms." in listing_after.output


def test_list_empty_store(runner, store):
    result = invoke(runner, store, "list")
    assert result.exit_code == 0
    assert "No alarms." in result.output


def test_update_label_and_disable(runner, store):
    create = invoke(runner, store, "set", "9:00am", "--days", "daily", "--label", "Gym")
    alarm_id = _extract_id(create.output)

    update = invoke(runner, store, "update", alarm_id, "--label", "Gym time", "--disable")
    assert update.exit_code == 0, update.output
    assert "Gym time" in update.output
    assert "disabled" in update.output

    listing = invoke(runner, store, "list", "--all")
    assert "Gym time" in listing.output


def test_update_with_no_flags_is_an_error(runner, store):
    create = invoke(runner, store, "set", "9:00am", "--days", "daily")
    alarm_id = _extract_id(create.output)
    result = invoke(runner, store, "update", alarm_id)
    assert result.exit_code != 0


def test_show_and_delete_unknown_id_report_not_found(runner, store):
    result = invoke(runner, store, "show", "does-not-exist")
    assert result.exit_code != 0
    assert "No alarm found" in result.output

    result = invoke(runner, store, "delete", "does-not-exist")
    assert result.exit_code != 0
    assert "No alarm found" in result.output


def test_list_excludes_disabled_unless_all(runner, store):
    create = invoke(runner, store, "set", "9:00am", "--days", "daily", "--label", "Gym")
    alarm_id = _extract_id(create.output)
    invoke(runner, store, "update", alarm_id, "--disable")

    default_listing = invoke(runner, store, "list")
    assert "Gym" not in default_listing.output

    all_listing = invoke(runner, store, "list", "--all")
    assert "Gym" in all_listing.output
