"""In-memory alarm repository — the default for library/API use and tests."""

from __future__ import annotations

from alarm_clock.exceptions import AlarmNotFoundError
from alarm_clock.models import Alarm
from alarm_clock.repository.base import AlarmRepository


class InMemoryAlarmRepository(AlarmRepository):
    def __init__(self) -> None:
        self._alarms: dict[str, Alarm] = {}

    def add(self, alarm: Alarm) -> None:
        self._alarms[alarm.id] = alarm

    def get(self, alarm_id: str) -> Alarm:
        try:
            return self._alarms[alarm_id]
        except KeyError:
            raise AlarmNotFoundError(alarm_id) from None

    def list(self) -> list[Alarm]:
        return list(self._alarms.values())

    def update(self, alarm: Alarm) -> None:
        if alarm.id not in self._alarms:
            raise AlarmNotFoundError(alarm.id)
        self._alarms[alarm.id] = alarm

    def delete(self, alarm_id: str) -> None:
        try:
            del self._alarms[alarm_id]
        except KeyError:
            raise AlarmNotFoundError(alarm_id) from None
