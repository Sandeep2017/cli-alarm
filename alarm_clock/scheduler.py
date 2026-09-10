"""The `alarm run` foreground loop: polls for due alarms and "rings" them.

Ringing = printing a line. Each tick walks forward from the end of the
*previous* tick to "now", ringing every trigger crossed in between (not just
the most recent one) — so a slow tick (e.g. the machine was briefly asleep)
still rings alarms it missed, purely by re-consulting the stateless
`next_trigger_for` function, with no separate "already rung" bookkeeping
needed. The one thing this can't help with is a one-time alarm whose fire
time passed while `alarm run` wasn't running at all — there's no persisted
record of it ever having been due (see PLAN.md §11).
"""

from __future__ import annotations

import time as time_module
from datetime import datetime

from alarm_clock.models import Alarm, ScheduleKind
from alarm_clock.service import AlarmClock
from alarm_clock.strategies import next_trigger_for


def run_scheduler(clock: AlarmClock, poll_interval: float = 1.0) -> None:
    last_check = datetime.now()
    while True:
        time_module.sleep(poll_interval)
        last_check = _tick(clock, since=last_check)


def _tick(clock: AlarmClock, since: datetime) -> datetime:
    """Ring every trigger in (since, now] for every alarm, return `now`."""
    now = datetime.now()
    for alarm in clock.list_alarms():
        cursor = since
        while True:
            trigger = next_trigger_for(alarm, cursor)
            if trigger is None or trigger > now:
                break
            _ring(alarm, trigger)
            if alarm.schedule.kind == ScheduleKind.ONCE:
                clock.set_enabled(alarm.id, enabled=False)
                break  # disabled now; next_trigger_for would be None anyway
            cursor = trigger
    return now


def _ring(alarm: Alarm, trigger: datetime) -> None:
    # flush explicitly: stdout is block-buffered once it isn't a tty (e.g.
    # redirected to a log file), and `alarm run` is typically killed rather
    # than exited cleanly, so an unflushed ring would otherwise be lost.
    print(f"\N{ALARM CLOCK} {alarm.label or 'Alarm'} ({trigger:%H:%M})", flush=True)
