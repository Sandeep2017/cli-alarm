# cli-alarm

A small alarm clock CLI. See [PLAN.md](PLAN.md) for the full design.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# Recurring, at a time of day
alarm set 1:30pm --label "Wake up" --days weekdays
alarm set 09:00 --days daily --label "Gym"
alarm set 10:00am --days weekends --label "Sleep in"

# One-time, relative to now
alarm set --in 5m --label "Tea's ready"

# Recurring interval
alarm set --every 10m --label "Stretch"

alarm list                 # enabled alarms
alarm list --all           # include disabled/fired ones
alarm show <id>
alarm update <id> --label "New label" --enable   # or --disable
alarm delete <id>

alarm run                  # foreground loop; prints a line when an alarm rings
```

Alarms are stored in `~/.alarm-cli/alarms.json` by default. Override with
`--store <path>` on any command, or the `ALARM_STORE` env var.

## Test

```bash
pytest
```

## Known limitations (see PLAN.md §1/§11)

- No timezone support — uses the local system clock.
- No snooze or sound; "ringing" is a printed line from `alarm run`.
- A one-time (`--in`) alarm whose fire time passes while `alarm run` isn't
  active is silently missed — there's no persisted record of it.
