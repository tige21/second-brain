import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")

from agent.system_prompt import build_system_prompt


def test_prompt_contains_all_11_rules():
    prompt = build_system_prompt("[]", "[]")
    for i in range(1, 12):
        assert f"ПРАВИЛО {i}" in prompt, f"Missing ПРАВИЛО {i}"


def test_prompt_injects_today_events():
    prompt = build_system_prompt(today_events='[{"id":"abc"}]', today_tasks="[]")
    assert '{"id":"abc"}' in prompt


def test_prompt_injects_today_tasks():
    prompt = build_system_prompt(today_events="[]", today_tasks='[{"title":"купить молоко"}]')
    assert "купить молоко" in prompt


def test_prompt_injects_active_address():
    prompt = build_system_prompt("[]", "[]", active_address="дом: ул. Тверская 1")
    assert "дом: ул. Тверская 1" in prompt


def test_prompt_timezone_offset_applied():
    prompt = build_system_prompt("[]", "[]", timezone_offset=5)
    assert "UTC+5" in prompt
    assert "UTC+5" in prompt


def test_prompt_fallback_for_empty_events():
    prompt = build_system_prompt(today_events="", today_tasks="")
    assert "нет данных" in prompt


def test_prompt_contains_current_datetime():
    from datetime import datetime, timezone
    prompt = build_system_prompt("[]", "[]")
    year = str(datetime.now(timezone.utc).year)
    assert year in prompt


def test_prompt_pending_location_shown():
    prompt = build_system_prompt("[]", "[]", pending_location="ул. Пушкина 10")
    assert "ул. Пушкина 10" in prompt
