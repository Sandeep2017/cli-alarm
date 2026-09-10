"""JSON-file-backed alarm repository: atomic writes + a cross-process lock.

Two independent safety mechanisms, per PLAN.md §7:
- `filelock.FileLock` serializes concurrent CLI invocations (held across the
  full read-modify-write, not just the write).
- Atomic replace (temp file in the same directory + fsync + os.replace)
  protects against this process itself crashing mid-write.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from filelock import FileLock, Timeout as FileLockTimeout
from pydantic import ValidationError

from alarm_clock.exceptions import (
    AlarmNotFoundError,
    StorageCorruptionError,
    StorageLockTimeoutError,
)
from alarm_clock.models import Alarm
from alarm_clock.repository.base import AlarmRepository

DEFAULT_STORE_PATH = Path.home() / ".alarm-cli" / "alarms.json"
_LOCK_TIMEOUT_SECONDS = 5


class JSONFileAlarmRepository(AlarmRepository):
    def __init__(self, path: Path | str = DEFAULT_STORE_PATH):
        self.path = Path(path)
        self._lock = FileLock(str(self.path.with_suffix(".lock")), timeout=_LOCK_TIMEOUT_SECONDS)

    # -- CRUD -----------------------------------------------------------

    def add(self, alarm: Alarm) -> None:
        with self._locked():
            alarms = self._read()
            alarms[alarm.id] = alarm
            self._write(alarms)

    def get(self, alarm_id: str) -> Alarm:
        with self._locked():
            alarms = self._read()
            try:
                return alarms[alarm_id]
            except KeyError:
                raise AlarmNotFoundError(alarm_id) from None

    def list(self) -> list[Alarm]:
        with self._locked():
            return list(self._read().values())

    def update(self, alarm: Alarm) -> None:
        with self._locked():
            alarms = self._read()
            if alarm.id not in alarms:
                raise AlarmNotFoundError(alarm.id)
            alarms[alarm.id] = alarm
            self._write(alarms)

    def delete(self, alarm_id: str) -> None:
        with self._locked():
            alarms = self._read()
            if alarm_id not in alarms:
                raise AlarmNotFoundError(alarm_id)
            del alarms[alarm_id]
            self._write(alarms)

    # -- internals --------------------------------------------------------

    def _locked(self):
        try:
            return self._lock.acquire()
        except FileLockTimeout:
            raise StorageLockTimeoutError(
                f"Could not acquire lock on {self.path} within "
                f"{_LOCK_TIMEOUT_SECONDS}s. Is another `alarm` process stuck?"
            ) from None

    def _read(self) -> dict[str, Alarm]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text())
        except json.JSONDecodeError as exc:
            raise StorageCorruptionError(f"{self.path} is not valid JSON: {exc}") from exc
        try:
            alarms = [Alarm.model_validate(item) for item in raw]
        except ValidationError as exc:
            raise StorageCorruptionError(
                f"{self.path} contains data that doesn't match the Alarm schema: {exc}"
            ) from exc
        return {alarm.id: alarm for alarm in alarms}

    def _write(self, alarms: dict[str, Alarm]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [alarm.model_dump(mode="json") for alarm in alarms.values()]

        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".alarms-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as tmp_file:
                json.dump(payload, tmp_file, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            # Best-effort cleanup of the temp file if we didn't get to the
            # atomic rename; the real file is never touched by this branch.
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
