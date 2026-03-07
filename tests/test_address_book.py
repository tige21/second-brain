import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123")
os.environ.setdefault("OPENAI_API_KEY", "x")

import pytest
from unittest.mock import patch
from db.database import init_db


@pytest.fixture
def conn(tmp_path):
    c = init_db(str(tmp_path / "test.db"))
    yield c
    c.close()


def invoke_tool(conn, **kwargs):
    """Call address_book tool with patched get_conn."""
    with patch("agent.tools.address_book.get_conn", return_value=conn):
        from agent.tools.address_book import address_book
        return address_book.invoke(kwargs)


def test_save_and_list_address(conn):
    result = invoke_tool(conn, operation="save", name="дом", address="ул. Тверская 1", coords="55.75,37.61")
    assert "сохранён" in result

    result = invoke_tool(conn, operation="list")
    assert "дом" in result
    assert "ул. Тверская 1" in result


def test_switch_active_address(conn):
    invoke_tool(conn, operation="save", name="офис", address="ул. Арбат 10", coords="55.75,37.59")
    result = invoke_tool(conn, operation="switch", name="офис")
    assert "Активный адрес" in result
    assert "офис" in result


def test_switch_nonexistent_address(conn):
    result = invoke_tool(conn, operation="switch", name="дача")
    assert "не найден" in result


def test_delete_address(conn):
    invoke_tool(conn, operation="save", name="зал", address="ул. Спортивная 5", coords="55.76,37.60")
    result = invoke_tool(conn, operation="delete", name="зал")
    assert "удалён" in result

    result = invoke_tool(conn, operation="list")
    assert "зал" not in result


def test_get_active_when_none_set(conn):
    result = invoke_tool(conn, operation="get_active")
    assert "не задан" in result


def test_get_active_returns_json(conn):
    invoke_tool(conn, operation="save", name="дом", address="ул. Тверская 1", coords="55.75,37.61")
    invoke_tool(conn, operation="switch", name="дом")
    result = invoke_tool(conn, operation="get_active")
    data = json.loads(result)
    assert data["name"] == "дом"
    assert data["coords"] == "55.75,37.61"


def test_save_pending_without_pending_location(conn):
    result = invoke_tool(conn, operation="save_pending", name="дом")
    assert "Нет ожидающей геолокации" in result


def test_save_pending_with_pending_location(conn):
    from db.models import set_setting
    pending = json.dumps({"coords": "55.75,37.61", "address": "ул. Тверская 1"})
    set_setting(conn, "pending_location", pending)

    result = invoke_tool(conn, operation="save_pending", name="дом")
    assert "сохранена" in result

    result = invoke_tool(conn, operation="get_active")
    data = json.loads(result)
    assert data["name"] == "дом"


def test_unknown_operation(conn):
    result = invoke_tool(conn, operation="explode")
    assert "Неизвестная операция" in result


def test_list_empty_address_book(conn):
    result = invoke_tool(conn, operation="list")
    assert "пуста" in result
