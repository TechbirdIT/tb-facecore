# edge_client/tests/test_debounce.py
from datetime import datetime, timedelta

from edge_client.debounce import Debouncer


def test_first_punch_allowed():
    d = Debouncer(window_minutes=2)
    assert d.allow("D1", datetime(2026, 1, 1, 9, 0, 0)) is True


def test_repeat_within_window_suppressed():
    d = Debouncer(window_minutes=2)
    t0 = datetime(2026, 1, 1, 9, 0, 0)
    assert d.allow("D1", t0) is True
    assert d.allow("D1", t0 + timedelta(minutes=1)) is False


def test_after_window_allowed_again():
    d = Debouncer(window_minutes=2)
    t0 = datetime(2026, 1, 1, 9, 0, 0)
    d.allow("D1", t0)
    assert d.allow("D1", t0 + timedelta(minutes=3)) is True


def test_independent_per_device():
    d = Debouncer(window_minutes=2)
    t0 = datetime(2026, 1, 1, 9, 0, 0)
    assert d.allow("D1", t0) is True
    assert d.allow("D2", t0) is True
