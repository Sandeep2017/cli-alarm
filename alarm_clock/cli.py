"""click-based CLI for alarm_clock.

Every command builds an `AlarmClock` over a `JSONFileAlarmRepository` and
catches `AlarmError` at the top level so failures print as
``Error: ...`` instead of a traceback.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import click

from alarm_clock.exceptions import AlarmError
from alarm_clock.models import Alarm, DaysOfWeekSchedule, IntervalSchedule, OnceSchedule, ScheduleKind
from alarm_clock.repository.json_file import DEFAULT_STORE_PATH, JSONFileAlarmRepository
from alarm_clock.scheduler import run_scheduler
from alarm_clock.service import AlarmClock
from alarm_clock.strategies import next_trigger_for
from alarm_clock.time_utils import parse_duration, parse_time_of_day

_DAYS_CHOICES = [ScheduleKind.DAILY.value, ScheduleKind.WEEKDAYS.value, ScheduleKind.WEEKENDS.value]


def _store_path(store_option: Path | None) -> Path:
    if store_option is not None:
        return store_option
    env_value = os.environ.get("ALARM_STORE")
    if env_value:
        return Path(env_value)
    return DEFAULT_STORE_PATH


def _make_clock(store: Path | None) -> AlarmClock:
    return AlarmClock(repository=JSONFileAlarmRepository(_store_path(store)))


def _describe_schedule(schedule) -> str:
    if isinstance(schedule, DaysOfWeekSchedule):
        return f"{schedule.kind.value} at {schedule.time_of_day:%H:%M}"
    if isinstance(schedule, OnceSchedule):
        return f"once at {schedule.fire_at:%Y-%m-%d %H:%M}"
    if isinstance(schedule, IntervalSchedule):
        return f"every {schedule.every}"
    return str(schedule)  # pragma: no cover - exhaustive in practice


def _print_alarm(alarm: Alarm) -> None:
    status = "enabled" if alarm.enabled else "disabled"
    next_trigger = next_trigger_for(alarm, datetime.now())
    next_str = f"next: {next_trigger:%Y-%m-%d %H:%M}" if next_trigger else "next: -"
    label = alarm.label or "(no label)"
    click.echo(
        f"{alarm.id}  {label:<20}  {_describe_schedule(alarm.schedule):<28}  "
        f"{status:<8}  {next_str}"
    )


_store_option = click.option(
    "--store",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to the alarms JSON file (default: ~/.alarm-cli/alarms.json, "
    "or $ALARM_STORE if set).",
)


@click.group()
def main() -> None:
    """A small alarm clock CLI."""


@main.command("set")
@click.argument("time_text", required=False, metavar="TIME")
@click.option(
    "--days",
    type=click.Choice(_DAYS_CHOICES),
    default=None,
    help="Recur on these days; used together with TIME.",
)
@click.option("--in", "in_text", metavar="DURATION", default=None, help="One-time alarm, e.g. '5m'.")
@click.option("--every", "every_text", metavar="DURATION", default=None, help="Recurring interval, e.g. '10m'.")
@click.option("--label", default=None, help="Optional label for the alarm.")
@_store_option
def set_alarm(
    time_text: str | None,
    days: str | None,
    in_text: str | None,
    every_text: str | None,
    label: str | None,
    store: Path | None,
) -> None:
    """Create an alarm.

    \b
    Examples:
      alarm set 1:30pm --label "Wake up" --days weekdays
      alarm set --in 5m --label "Tea's ready"
      alarm set --every 10m --label "Stretch"
    """
    modes_given = [bool(time_text or days), bool(in_text), bool(every_text)]
    if sum(modes_given) == 0:
        raise click.UsageError("Specify TIME (with --days), --in, or --every.")
    if sum(modes_given) > 1:
        raise click.UsageError("TIME/--days, --in, and --every are mutually exclusive.")

    try:
        if in_text:
            fire_at = datetime.now() + parse_duration(in_text)
            schedule = OnceSchedule(fire_at=fire_at)
        elif every_text:
            schedule = IntervalSchedule(every=parse_duration(every_text), anchor=datetime.now())
        else:
            if not time_text or not days:
                raise click.UsageError("TIME requires --days (daily/weekdays/weekends).")
            schedule = DaysOfWeekSchedule(kind=ScheduleKind(days), time_of_day=parse_time_of_day(time_text))

        alarm = _make_clock(store).create_alarm(schedule=schedule, label=label)
    except AlarmError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Created alarm {alarm.id}")
    _print_alarm(alarm)


@main.command("list")
@click.option("--all", "show_all", is_flag=True, help="Also show disabled alarms.")
@_store_option
def list_alarms(show_all: bool, store: Path | None) -> None:
    """List alarms."""
    try:
        alarms = _make_clock(store).list_alarms()
    except AlarmError as exc:
        raise click.ClickException(str(exc)) from exc

    if not show_all:
        alarms = [a for a in alarms if a.enabled]
    if not alarms:
        click.echo("No alarms.")
        return
    for alarm in sorted(alarms, key=lambda a: a.created_at):
        _print_alarm(alarm)


@main.command("show")
@click.argument("alarm_id")
@_store_option
def show_alarm(alarm_id: str, store: Path | None) -> None:
    """Show one alarm."""
    try:
        alarm = _make_clock(store).get_alarm(alarm_id)
    except AlarmError as exc:
        raise click.ClickException(str(exc)) from exc
    _print_alarm(alarm)


@main.command("update")
@click.argument("alarm_id")
@click.option("--label", default=None, help="New label.")
@click.option("--enable", "enabled", flag_value=True, default=None, help="Enable the alarm.")
@click.option("--disable", "enabled", flag_value=False, help="Disable the alarm.")
@_store_option
def update_alarm(alarm_id: str, label: str | None, enabled: bool | None, store: Path | None) -> None:
    """Update an alarm's label and/or enabled state."""
    kwargs = {}
    if label is not None:
        kwargs["label"] = label
    if enabled is not None:
        kwargs["enabled"] = enabled
    if not kwargs:
        raise click.UsageError("Nothing to update: pass --label and/or --enable/--disable.")

    try:
        alarm = _make_clock(store).update_alarm(alarm_id, **kwargs)
    except AlarmError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Updated alarm {alarm.id}")
    _print_alarm(alarm)


@main.command("delete")
@click.argument("alarm_id")
@_store_option
def delete_alarm(alarm_id: str, store: Path | None) -> None:
    """Delete an alarm."""
    try:
        _make_clock(store).delete_alarm(alarm_id)
    except AlarmError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Deleted alarm {alarm_id}")


@main.command("run")
@click.option("--poll-interval", type=float, default=1.0, help="Seconds between checks.")
@_store_option
def run(poll_interval: float, store: Path | None) -> None:
    """Run the foreground loop that rings alarms as they come due."""
    clock = _make_clock(store)
    click.echo(f"Watching {clock.repository.path} — press Ctrl+C to stop.")
    try:
        run_scheduler(clock, poll_interval=poll_interval)
    except KeyboardInterrupt:
        click.echo("\nStopped.")
        sys.exit(0)
    except AlarmError as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
