"""Custom exception hierarchy for the alarm_clock package.

Callers (CLI, future API) should only ever need to catch ``AlarmError`` to
handle everything this package can raise, instead of leaking
``pydantic.ValidationError`` or raw ``OSError``/``json`` errors upward.
"""


class AlarmError(Exception):
    """Base class for every exception raised by alarm_clock."""


class AlarmNotFoundError(AlarmError):
    """Raised when looking up, updating, or deleting an unknown alarm id."""

    def __init__(self, alarm_id: str):
        super().__init__(f"No alarm found with id {alarm_id!r}")
        self.alarm_id = alarm_id


class InvalidAlarmError(AlarmError):
    """Raised when alarm input (schedule, label, ...) fails validation."""


class InvalidTimeFormatError(InvalidAlarmError):
    """Raised when a time-of-day or duration string can't be parsed."""


class StorageError(AlarmError):
    """Base class for repository/storage failures."""


class StorageLockTimeoutError(StorageError):
    """Raised when the on-disk lock for the alarm store couldn't be acquired."""


class StorageCorruptionError(StorageError):
    """Raised when the alarm store file exists but isn't valid/parseable."""
