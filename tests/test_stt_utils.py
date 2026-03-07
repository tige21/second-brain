import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")

from services.openai_stt import format_duration


def test_seconds_only():
    assert format_duration(25) == "25 сек"


def test_exactly_one_minute():
    assert format_duration(60) == "1 мин 0 сек"


def test_minutes_and_seconds():
    assert format_duration(90) == "1 мин 30 сек"


def test_long_recording():
    assert format_duration(185) == "3 мин 5 сек"


def test_zero_seconds():
    assert format_duration(0) == "0 сек"


def test_voice_threshold_boundary():
    """Messages > 30 sec should get 🎙️ prefix — verify threshold values."""
    assert format_duration(30) == "30 сек"   # exactly at threshold
    assert format_duration(31) == "31 сек"   # just above — gets long prefix
