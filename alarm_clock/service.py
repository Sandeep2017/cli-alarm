"""AlarmClock: the storage-agnostic domain service.

This is the class a future API layer wraps directly — it has no knowledge
of click/argparse, only of `models`, `strategies`, `exceptions`, and an
injected `AlarmRepository`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from alarm_clock.exceptions import InvalidAlarmError
from alarm_clock.models import Alarm, Schedule
from alarm_clock.repository.base import AlarmRepository
from alarm_clock.repository.memory import InMemoryAlarmRepository

# Sentinel distinguishing "field not passed" from "field explicitly set to None"
# in update_alarm's keyword arguments.
_UNSET = object()


class AlarmClock:
    def __init__(self, repository: AlarmRepository | None = None):
        self.repository = repository or InMemoryAlarmRepository()

    def create_alarm(self, schedule: Schedule, label: str | None = None) -> Alarm:
        try:
            alarm = Alarm(
                id=uuid.uuid4().hex,
                label=label,
                schedule=schedule,
                created_at=datetime.now(),
            )
        except ValidationError as exc:
            raise InvalidAlarmError(str(exc)) from exc
        self.repository.add(alarm)
        return alarm

    def get_alarm(self, alarm_id: str) -> Alarm:
        return self.repository.get(alarm_id)

    def list_alarms(self) -> list[Alarm]:
        return self.repository.list()

    def update_alarm(
        self,
        alarm_id: str,
        *,
        label: Any = _UNSET,
        schedule: Any = _UNSET,
        enabled: Any = _UNSET,
    ) -> Alarm:
        current = self.repository.get(alarm_id)
        updates: dict[str, Any] = {}
        if label is not _UNSET:
            updates["label"] = label
        if schedule is not _UNSET:
            updates["schedule"] = schedule
        if enabled is not _UNSET:
            updates["enabled"] = enabled

        try:
            updated = current.model_copy(update=updates)
            # model_copy doesn't re-run validation; force it explicitly so
            # bad updates (e.g. an invalid schedule) are still caught here.
            updated = Alarm.model_validate(updated.model_dump())
        except ValidationError as exc:
            raise InvalidAlarmError(str(exc)) from exc

        self.repository.update(updated)
        return updated

    def set_enabled(self, alarm_id: str, enabled: bool) -> Alarm:
        return self.update_alarm(alarm_id, enabled=enabled)

    def delete_alarm(self, alarm_id: str) -> None:
        self.repository.delete(alarm_id)
