"""Pydantic domain models: alarms and their schedules.

Schedules are a discriminated union on `kind`. DAILY/WEEKDAYS/WEEKENDS all
share one model (`DaysOfWeekSchedule`) since they only differ in *which*
weekdays count, not in shape — that day-set is derived from `kind` by
`strategies.WEEKDAYS_BY_KIND`, not stored redundantly here.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator


class ScheduleKind(str, Enum):
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    ONCE = "once"
    INTERVAL = "interval"


class DaysOfWeekSchedule(BaseModel):
    """Fires at `time_of_day` on every day matching `kind`."""

    kind: Literal[ScheduleKind.DAILY, ScheduleKind.WEEKDAYS, ScheduleKind.WEEKENDS]
    time_of_day: time


class OnceSchedule(BaseModel):
    """Fires once at `fire_at`, a fixed absolute datetime resolved at
    creation time (from e.g. ``--in 5m`` + "now")."""

    kind: Literal[ScheduleKind.ONCE] = ScheduleKind.ONCE
    fire_at: datetime


class IntervalSchedule(BaseModel):
    """Fires repeatedly every `every`, starting from `anchor` (= created_at)."""

    kind: Literal[ScheduleKind.INTERVAL] = ScheduleKind.INTERVAL
    every: timedelta
    anchor: datetime

    @field_validator("every")
    @classmethod
    def _every_must_be_positive(cls, value: timedelta) -> timedelta:
        if value <= timedelta(0):
            raise ValueError("interval `every` must be positive")
        return value


Schedule = Annotated[
    Union[DaysOfWeekSchedule, OnceSchedule, IntervalSchedule],
    Field(discriminator="kind"),
]


class Alarm(BaseModel):
    id: str
    label: str | None = None
    schedule: Schedule
    enabled: bool = True
    created_at: datetime
