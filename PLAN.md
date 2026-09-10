# PLAN.md — Python Alarm Clock CLI

Design plan for a `pip`-installable `alarm` CLI.

## 1. Goals & non-goals

**Goals**
- `AlarmClock` domain class with CRUD, usable standalone (no CLI/click import
  inside it) so a future FastAPI layer can wrap it directly.
- Storage abstracted behind a repository interface: in-memory today, JSON file
  next, DB-backed later, without touching `AlarmClock`.
- JSON storage survives a crash mid-write (atomic replace) and mid-process
  concurrent access (file lock).
- Alarm schedules (daily / weekdays / weekends / one-time / interval)
  implemented via the Strategy pattern.
- Pydantic models for all validated data; a small custom exception hierarchy
  instead of leaking `ValueError`/`pydantic.ValidationError` everywhere.
- `alarm run` foreground loop that "rings" (prints) alarms when due.

**Non-goals (explicitly out of scope for v1)**
- Multi-user / concurrent-writer safety beyond "don't corrupt the file if the
  process crashes." Locking is for crash-safety, not for coordinating many
  simultaneous users.
- Timezones — everything uses naive local time (`datetime.now()`).
- Snooze, sound, desktop notifications — "ringing" is a printed line.
- A real daemon (systemd/launchd unit, background fork). `alarm run` is a
  blocking foreground process the user starts themselves.

## 2. Key design decisions

| Decision | Choice | Why |
|---|---|---|
| CLI framework | **click** | Subcommands (`set`/`list`/`delete`/...), option parsing, and `CliRunner` for tests are all less boilerplate than argparse. Already taking on `pydantic` as a dependency, so one more small dep is fine. |
| Time model | naive `datetime`/`time`, local system clock | Avoids timezone/DST complexity the requirements didn't ask for. Documented as a known limitation. |
| Trigger computation | **stateless / pure function** `next_trigger(schedule, after) -> datetime | None` | A schedule + "current time" is enough to compute the next fire time for every schedule kind (see §6). No mutable "last fired at" bookkeeping needs to live in storage — keeps the repository dumb and the JSON file simple. |
| Duplicate-ring suppression | tracked **in-memory, only inside the `alarm run` process** | The loop remembers `(alarm_id, trigger_time)` pairs it already printed this session. Restarting `alarm run` after a missed one-time alarm's fire time means it won't re-ring — acceptable for a personal tool, called out in §11 as a known limitation. |
| Locking primitive | **`filelock`** (third-party, cross-platform) | Rolling our own `fcntl`/`msvcrt` cross-platform shim is exactly the kind of over-engineering to avoid; `filelock` is tiny and battle-tested. |
| Days-of-week strategies | explicit `ScheduleKind.DAILY`/`WEEKDAYS`/`WEEKENDS` values, but **one `DaysOfWeekStrategy`** class behind all three, not three separate classes | Explicit kinds make the model/CLI/`list` output read clearly (`daily`, not `days_of_week`), while the strategy still only differs in *which days count* — one class, told which weekday set to use via a `kind → weekdays` lookup (§6), stays the Strategy pattern without three near-duplicate classes. |

## 3. Package structure

```
alarm_clock/
├── __init__.py
├── exceptions.py       # AlarmError and subclasses
├── models.py            # Pydantic: Alarm, Schedule variants (discriminated union)
├── time_utils.py        # parse "1:30pm", "13:30", "5m", "10m" strings
├── strategies.py         # Strategy interface + concrete strategies + factory
├── repository/
│   ├── __init__.py         # AlarmRepository ABC
│   ├── memory.py            # InMemoryAlarmRepository
│   └── json_file.py          # JSONFileAlarmRepository (atomic write + lock)
├── service.py            # AlarmClock: CRUD, wraps a repository
├── scheduler.py           # the `alarm run` polling loop
└── cli.py                 # click commands, wires everything together

tests/
├── test_models.py
├── test_time_utils.py
├── test_strategies.py
├── test_repository_memory.py
├── test_repository_json.py
├── test_service.py
├── test_scheduler.py
└── test_cli.py

pyproject.toml
PLAN.md
README.md
```

`__main__.py` is not needed if `pyproject.toml` declares a console-script entry
point (`alarm = "alarm_clock.cli:main"`); add one only if `python -m
alarm_clock` support is wanted too.

## 4. Domain models (`models.py`)

```python
class ScheduleKind(str, Enum):
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    ONCE = "once"          # --in 5m
    INTERVAL = "interval"   # --every 10m

# DAILY / WEEKDAYS / WEEKENDS share one model — they differ only in which
# weekdays count, and that's derived from `kind` (see §6), not stored here.
class DaysOfWeekSchedule(BaseModel):
    kind: Literal[ScheduleKind.DAILY, ScheduleKind.WEEKDAYS, ScheduleKind.WEEKENDS]
    time_of_day: time

class OnceSchedule(BaseModel):
    kind: Literal[ScheduleKind.ONCE] = ScheduleKind.ONCE
    fire_at: datetime          # resolved once, at creation time, from "--in 5m"

class IntervalSchedule(BaseModel):
    kind: Literal[ScheduleKind.INTERVAL] = ScheduleKind.INTERVAL
    every: timedelta
    anchor: datetime           # = created_at; next fire = anchor + n*every

Schedule = Annotated[
    Union[DaysOfWeekSchedule, OnceSchedule, IntervalSchedule],
    Field(discriminator="kind"),
]

class Alarm(BaseModel):
    id: str                    # uuid4 hex, generated server-side
    label: str | None = None
    schedule: Schedule
    enabled: bool = True
    created_at: datetime
```

Notes:
- `id` is never user-supplied on create; `update`/`delete` take it as a lookup
  key.
- `OnceSchedule.fire_at` and `IntervalSchedule.anchor` are computed once at
  creation time (from `--in`/`--every` + "now") and then stored as absolute
  values — so re-parsing on load never depends on when the file happens to be
  read.
- Pydantic handles: `every > timedelta(0)`, `fire_at`/`time_of_day`
  well-formed, `kind` one of its allowed literals. Cross-field or "does this
  alarm even make sense"
  errors raise our own exceptions (§5), not raw `pydantic.ValidationError`,
  by catching it at the model-construction boundary in `service.py`.

## 5. Exceptions (`exceptions.py`)

```
AlarmError                     # base for everything this package raises
├── AlarmNotFoundError         # update/delete/get on unknown id
├── InvalidAlarmError          # bad schedule/time/label input (wraps pydantic ValidationError)
├── InvalidTimeFormatError     # "1:30pm" / "5m" parsing failures (subclass of InvalidAlarmError)
└── StorageError               # base for repository failures
    ├── StorageLockTimeoutError  # couldn't acquire the file lock in time
    └── StorageCorruptionError   # JSON file exists but isn't valid/parseable
```

CLI layer catches `AlarmError` at the top of each command and prints
`Error: {message}` + exits non-zero, instead of a traceback.

## 6. Strategy pattern for scheduling (`strategies.py`)

```python
class AlarmStrategy(Protocol):
    def next_trigger(self, after: datetime) -> datetime | None:
        """First fire time strictly after `after`, or None if this alarm
        will never fire again (e.g. a Once schedule whose fire_at has passed)."""

WEEKDAYS_BY_KIND: dict[ScheduleKind, frozenset[int]] = {
    ScheduleKind.DAILY: frozenset(range(7)),      # Mon..Sun
    ScheduleKind.WEEKDAYS: frozenset(range(5)),   # Mon..Fri
    ScheduleKind.WEEKENDS: frozenset({5, 6}),      # Sat, Sun
}

class DaysOfWeekStrategy:
    def __init__(self, schedule: DaysOfWeekSchedule):
        self.schedule = schedule
        self.weekdays = WEEKDAYS_BY_KIND[schedule.kind]
    def next_trigger(self, after): ...
        # walk forward day by day (max 7 iterations) looking for a weekday
        # in self.weekdays where time_of_day > after's time-of-day
        # (or any day past `after`'s date), combine date + time_of_day.

class OnceStrategy:
    def __init__(self, schedule: OnceSchedule): ...
    def next_trigger(self, after):
        return schedule.fire_at if schedule.fire_at > after else None

class IntervalStrategy:
    def __init__(self, schedule: IntervalSchedule): ...
    def next_trigger(self, after):
        # smallest anchor + n*every that is > after
        elapsed = after - schedule.anchor
        n = elapsed // schedule.every + 1
        return schedule.anchor + n * schedule.every

STRATEGIES: dict[ScheduleKind, type[AlarmStrategy]] = {
    ScheduleKind.DAILY: DaysOfWeekStrategy,
    ScheduleKind.WEEKDAYS: DaysOfWeekStrategy,
    ScheduleKind.WEEKENDS: DaysOfWeekStrategy,
    ScheduleKind.ONCE: OnceStrategy,
    ScheduleKind.INTERVAL: IntervalStrategy,
}

def strategy_for(schedule: Schedule) -> AlarmStrategy:
    return STRATEGIES[schedule.kind](schedule)
```

`Alarm.next_trigger(after)` on the model (or a free function taking an
`Alarm`) delegates to `strategy_for(alarm.schedule).next_trigger(after)`,
returning `None` immediately if `alarm.enabled` is `False`.

## 7. Storage abstraction (`repository/`)

```python
class AlarmRepository(ABC):
    def add(self, alarm: Alarm) -> None: ...
    def get(self, alarm_id: str) -> Alarm: ...          # raises AlarmNotFoundError
    def list(self) -> list[Alarm]: ...
    def update(self, alarm: Alarm) -> None: ...          # raises AlarmNotFoundError
    def delete(self, alarm_id: str) -> None: ...          # raises AlarmNotFoundError
```

**`InMemoryAlarmRepository`** — `dict[str, Alarm]` behind a small lock-free
wrapper. Default for unit tests and for `AlarmClock()` used as a library.

**`JSONFileAlarmRepository(path: Path)`** — the default for the CLI:
- Every method acquires a `filelock.FileLock(path.with_suffix(".lock"))`
  before touching the file (short timeout, e.g. 5s, raising
  `StorageLockTimeoutError` on failure) — held for the duration of a full
  read-modify-write, not just the write, so two CLI invocations racing each
  other still serialize correctly.
- **Read**: if the file doesn't exist, treat as empty list. If it exists but
  fails `json.loads` or fails `Alarm` validation, raise
  `StorageCorruptionError` rather than silently discarding data.
- **Write (atomic)**: serialize the full alarm list to a temp file in the
  *same directory* (`tempfile.NamedTemporaryFile(dir=..., delete=False)`),
  `flush()` + `os.fsync()`, then `os.replace(tmp_path, path)`. `os.replace` is
  atomic on POSIX and Windows, so a crash before the final rename leaves the
  original file untouched, and a crash after leaves the new file fully
  written — there is no window where a half-written file is the live one.
- **Location**: `Path.home() / ".alarm-cli" / "alarms.json"` — an absolute
  path from `$HOME`, never from `cwd`, so the CLI behaves identically no
  matter which directory it's invoked from. The repository
  `mkdir(parents=True, exist_ok=True)`s that directory on first write if it
  doesn't exist yet (fresh install has no `~/.alarm-cli/`).
- **Override**: `--store <path>` CLI option (or `ALARM_STORE` env var, `--store`
  taking precedence) / `AlarmClock(repository=JSONFileAlarmRepository(path))`
  constructor arg for library use and for tests (point it at a temp dir).

This is the seam a later `SqlAlarmRepository` implements against — same ABC,
`service.py` and `cli.py` don't change.

## 8. `AlarmClock` service (`service.py`)

Framework-agnostic; only depends on `models`, `strategies`, `exceptions`, and
an injected `AlarmRepository`. This is the class an eventual API layer calls
directly.

```python
class AlarmClock:
    def __init__(self, repository: AlarmRepository | None = None):
        self.repository = repository or InMemoryAlarmRepository()

    def create_alarm(self, schedule: Schedule, label: str | None = None) -> Alarm: ...
    def get_alarm(self, alarm_id: str) -> Alarm: ...
    def list_alarms(self) -> list[Alarm]: ...
    def update_alarm(self, alarm_id: str, *, label=..., schedule=..., enabled=...) -> Alarm: ...
    def delete_alarm(self, alarm_id: str) -> None: ...
    def set_enabled(self, alarm_id: str, enabled: bool) -> Alarm: ...
```

`update_alarm`'s unset-vs-explicit-None fields use a sentinel (or
`model_copy(update=...)` with only provided kwargs) so "don't touch this
field" is distinguishable from "set it to None". Any `pydantic.ValidationError`
raised while building/copying the model is caught here and re-raised as
`InvalidAlarmError`.

## 9. Time/duration parsing (`time_utils.py`)

Pure functions, no CLI dependency, so the future API can reuse them if it
also accepts human strings:

```python
def parse_time_of_day(text: str) -> time:
    # "13:30" (HH:MM, 24h) or "1:30pm" / "1:30PM" (12h + am/pm)
    # raises InvalidTimeFormatError on anything else

def parse_duration(text: str) -> timedelta:
    # "<int>m" minutes, "<int>h" hours, "<int>s" seconds — e.g. "5m", "10m", "1h"
    # raises InvalidTimeFormatError on anything else
```

## 10. CLI (`cli.py`, click)

```
alarm set <TIME> --days {daily,weekdays,weekends} [--label TEXT]
alarm set --in <DURATION> [--label TEXT]
alarm set --every <DURATION> [--label TEXT]

alarm list [--all]              # --all also shows disabled/fired one-shots
alarm show <ID>
alarm update <ID> [--label TEXT] [--enable | --disable]
alarm delete <ID>

alarm run [--store PATH] [--poll-interval SECONDS]
```

- `<TIME>` positional and `--days` go together; `--in` and `--every` are each
  their own mode. These three modes are mutually exclusive — validated in a
  click callback (`click.UsageError` if more than one mode's flags are
  present, or if `<TIME>` is given without `--days` or vice versa).
- Matches the example exactly: `alarm set 1:30pm --label "Wake up" --days
  weekdays`.
- Every command builds an `AlarmClock(repository=JSONFileAlarmRepository(store_path))`
  and catches `AlarmError` → `click.echo(f"Error: {e}", err=True)` +
  `sys.exit(1)`.
- `list`/`show` print each alarm's id, label, human-readable schedule, and
  (via `strategy_for(...).next_trigger(datetime.now())`) its next fire time.

## 11. Scheduler / "ringing" (`scheduler.py`, driven by `alarm run`)

```python
def run_scheduler(clock: AlarmClock, poll_interval: float = 1.0) -> None:
    last_check = datetime.now()
    while True:
        time.sleep(poll_interval)
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
            print(f"⏰ {alarm.label or 'Alarm'} ({trigger:%H:%M})")
            if alarm.schedule.kind == ScheduleKind.ONCE:
                clock.set_enabled(alarm.id, enabled=False)
                break  # disabled now; next_trigger_for would be None anyway
            cursor = trigger
    return now
```

- Re-fetches `clock.list_alarms()` every cycle, so alarms added/edited by a
  separate `alarm set` invocation while `run` is active are picked up without
  a restart.
- Walking forward from the *previous* tick's `now` (rather than a fixed
  lookback window) means a slow tick — e.g. the machine briefly slept —
  still rings everything crossed in the gap, including more than one
  interval boundary, with no separate "already rung" set needed: it falls
  straight out of `next_trigger_for` being a pure function of `(schedule,
  after)`.
- One-time alarms disable themselves right after ringing, so `next_trigger`
  also naturally returns `None` for them going forward — belt and suspenders
  with §2's "stateless" design, since a disabled alarm short-circuits before
  the strategy is even consulted.
- **Known limitation** (documented, not fixed for v1): if `alarm run` isn't
  running at all when a one-time alarm's `fire_at` passes, it is silently
  missed — `since` resets to "now" on every fresh `alarm run` start, and
  there's no persisted "did we ever ring this" flag. Acceptable for a
  personal tool; flagged in README as a possible future addition.
- Ctrl+C exits cleanly (`KeyboardInterrupt` caught in `cli.py`'s `run`
  command). The ring's `print(..., flush=True)` matters here too: stdout is
  block-buffered once it isn't a tty (e.g. redirected to a log file), and
  `alarm run` is typically killed rather than exited cleanly, so an
  unflushed ring would otherwise be lost.

## 12. Testing

- **pytest**, plus **freezegun** (or manual `datetime` monkeypatching) to
  make `next_trigger` tests deterministic.
- `test_strategies.py`: table-driven — for each schedule kind, given a
  fixed "now", assert the expected next trigger (including edge cases: a
  `DaysOfWeekSchedule` where today's slot already passed → rolls to next
  matching weekday; `IntervalSchedule` where `after` lands exactly on a
  boundary; `OnceSchedule` after its `fire_at`→ `None`).
- `test_repository_json.py`: round-trip write/read; corrupt-file →
  `StorageCorruptionError`; simulate a crash by killing the process between
  temp-file write and `os.replace` (hard to test directly — instead assert
  that a leftover `*.tmp` file from a previous crash doesn't affect reads,
  and that the real file is only ever valid JSON after any write completes).
- `test_service.py`: CRUD against `InMemoryAlarmRepository`, unknown-id →
  `AlarmNotFoundError`, invalid schedule → `InvalidAlarmError`.
- `test_cli.py`: click's `CliRunner`, using a temp dir for `--store`, covering
  the exact example from the requirements plus each mode (`--in`, `--every`,
  each `--days` value) and the error paths (mutually-exclusive flags, bad
  time format).
- `test_scheduler.py`: fake clock advanced manually across a few poll
  cycles, asserting printed output and that a `once` alarm only rings once.

## 13. Dependencies

- `pydantic>=2`
- `click>=8`
- `filelock`
- dev: `pytest`, `freezegun`

## 14. Future extensions (not built now, but the seams for them)

- **API layer**: a `FastAPI` app importing `AlarmClock` and the same Pydantic
  `Alarm`/`Schedule` models directly as request/response bodies — no
  translation layer needed since validation already lives in `models.py`.
- **Database storage**: a `SqlAlarmRepository` (e.g. SQLModel/SQLAlchemy)
  implementing `AlarmRepository`; `service.py`/`cli.py` unchanged.
- **Notifiers**: today `scheduler.py` hardcodes `print(...)`; if sound/desktop
  notifications are ever wanted, extract a `Notifier` interface
  (`.notify(alarm)`) the loop calls instead — straightforward, not built
  until it's actually needed.
- **Timezones, snooze, missed-alarm catch-up on restart** — explicitly
  deferred (§1).

## 15. Suggested build order

1. `exceptions.py`, `models.py` (+ `test_models.py`)
2. `time_utils.py` (+ tests)
3. `strategies.py` (+ tests) — the trickiest logic, get it solid early
4. `repository/memory.py` + `AlarmRepository` ABC (+ tests)
5. `service.py` (`AlarmClock`) against the in-memory repo (+ tests)
6. `repository/json_file.py` (atomic + locked) (+ tests)
7. `cli.py` (`set`/`list`/`show`/`update`/`delete`) (+ tests)
8. `scheduler.py` + `alarm run` (+ tests)
9. `pyproject.toml` packaging, README usage docs
