import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime, timezone, timedelta


def should_send_departure_alert(
    event_start: datetime,
    travel_minutes: int,
    buffer_minutes: int = 10,
    alert_window_minutes: int = 125,
) -> bool:
    """Returns True if we should send departure alert now."""
    now = datetime.now(timezone.utc)
    depart_at = event_start - timedelta(minutes=travel_minutes + buffer_minutes)
    minutes_until_depart = (depart_at - now).total_seconds() / 60
    return -15 <= minutes_until_depart <= alert_window_minutes


def test_should_alert_within_window():
    now = datetime.now(timezone.utc)
    event_start = now + timedelta(minutes=60)
    assert should_send_departure_alert(event_start, travel_minutes=30) is True


def test_should_not_alert_far_future():
    now = datetime.now(timezone.utc)
    event_start = now + timedelta(hours=5)
    assert should_send_departure_alert(event_start, travel_minutes=30) is False


def test_should_alert_slightly_past_depart():
    # event in 5 min, travel=5 + buffer=10 = depart was 10 min ago → within -15 window
    now = datetime.now(timezone.utc)
    event_start = now + timedelta(minutes=5)
    assert should_send_departure_alert(event_start, travel_minutes=5, buffer_minutes=10) is True


def test_should_not_alert_too_late():
    now = datetime.now(timezone.utc)
    event_start = now - timedelta(minutes=30)
    assert should_send_departure_alert(event_start, travel_minutes=20) is False
