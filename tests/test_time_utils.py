from datetime import time, timedelta

import pytest

from alarm_clock.exceptions import InvalidTimeFormatError
from alarm_clock.time_utils import parse_duration, parse_time_of_day


@pytest.mark.parametrize(
    "text, expected",
    [
        ("13:30", time(13, 30)),
        ("1:30pm", time(13, 30)),
        ("1:30PM", time(13, 30)),
        ("1:30 pm", time(13, 30)),
        ("1:30am", time(1, 30)),
        ("00:00", time(0, 0)),
        ("12:00am", time(0, 0)),
        ("12:00pm", time(12, 0)),
    ],
)
def test_parse_time_of_day_valid(text, expected):
    assert parse_time_of_day(text) == expected


@pytest.mark.parametrize("text", ["25:00", "13:30xm", "not a time", ""])
def test_parse_time_of_day_invalid(text):
    with pytest.raises(InvalidTimeFormatError):
        parse_time_of_day(text)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5m", timedelta(minutes=5)),
        ("10s", timedelta(seconds=10)),
        ("1h", timedelta(hours=1)),
        ("  5m  ", timedelta(minutes=5)),
        ("5M", timedelta(minutes=5)),
    ],
)
def test_parse_duration_valid(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["0m", "-5m", "5", "m5", "5 minutes", ""])
def test_parse_duration_invalid(text):
    with pytest.raises(InvalidTimeFormatError):
        parse_duration(text)
