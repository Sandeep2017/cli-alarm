"""The storage abstraction every alarm repository implements.

`AlarmClock` (service.py) only ever talks to this interface, so swapping
in-memory -> JSON file -> a future database is invisible to it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from alarm_clock.models import Alarm


class AlarmRepository(ABC):
    @abstractmethod
    def add(self, alarm: Alarm) -> None: ...

    @abstractmethod
    def get(self, alarm_id: str) -> Alarm:
        """Raises AlarmNotFoundError if no alarm has this id."""

    @abstractmethod
    def list(self) -> list[Alarm]: ...

    @abstractmethod
    def update(self, alarm: Alarm) -> None:
        """Raises AlarmNotFoundError if no alarm has this id."""

    @abstractmethod
    def delete(self, alarm_id: str) -> None:
        """Raises AlarmNotFoundError if no alarm has this id."""
