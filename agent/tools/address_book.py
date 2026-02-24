import json
from langchain_core.tools import tool
from db.database import get_conn
from db.models import (
    save_address, get_address, list_addresses, delete_address,
    set_setting, get_setting,
)


@tool
def address_book(operation: str, name: str = None, address: str = None, coords: str = None) -> str:
    """
    Manage named address book.

    operations:
    - "save": save new address. Requires name, address (text), coords ("lat,lon").
    - "save_pending": save the pending GPS location with a name. Requires name only.
    - "list": list all saved addresses.
    - "switch": set active address by name. Requires name.
    - "delete": delete address by name. Requires name.
    - "get_active": get the currently active address.

    Examples:
    - address_book(operation="save", name="офис", address="ул. Тверская 22", coords="55.76,37.61")
    - address_book(operation="save_pending", name="зал")
    - address_book(operation="switch", name="дом")
    - address_book(operation="list")
    - address_book(operation="delete", name="старый офис")
    """
    conn = get_conn()

    if operation == "save":
        if not name or not address or not coords:
            return "Ошибка: укажи name, address и coords для операции save"
        save_address(conn, name.lower(), address, coords)
        return f"✅ Адрес '{name}' сохранён: {address}"

    elif operation == "save_pending":
        if not name:
            return "Ошибка: укажи name для операции save_pending"
        pending_json = get_setting(conn, 'pending_location')
        if not pending_json:
            return "Нет ожидающей геолокации. Сначала отправь GPS-точку."
        pending = json.loads(pending_json)
        save_address(conn, name.lower(), pending.get('address', 'неизвестно'), pending['coords'])
        set_setting(conn, 'active_address', name.lower())
        set_setting(conn, 'pending_location', '')
        return f"✅ Геолокация сохранена как '{name}': {pending.get('address', pending['coords'])}"

    elif operation == "list":
        addresses = list_addresses(conn)
        active = get_setting(conn, 'active_address') or 'не задан'
        if not addresses:
            return "Адресная книга пуста. Отправь GPS-точку или используй 'save'."
        lines = [f"📍 Адресная книга (активный: {active}):"]
        for a in addresses:
            marker = "→ " if a['name'] == active else "   "
            lines.append(f"{marker}{a['name']}: {a['address']}")
        return "\n".join(lines)

    elif operation == "switch":
        if not name:
            return "Ошибка: укажи name для операции switch"
        addr = get_address(conn, name.lower())
        if not addr:
            all_names = ', '.join(a['name'] for a in list_addresses(conn))
            return f"Адрес '{name}' не найден. Доступные: {all_names or 'нет'}"
        set_setting(conn, 'active_address', name.lower())
        return f"✅ Активный адрес: {name} ({addr['address']})"

    elif operation == "delete":
        if not name:
            return "Ошибка: укажи name для операции delete"
        if not get_address(conn, name.lower()):
            return f"Адрес '{name}' не найден"
        delete_address(conn, name.lower())
        active = get_setting(conn, 'active_address')
        if active == name.lower():
            set_setting(conn, 'active_address', '')
        return f"✅ Адрес '{name}' удалён"

    elif operation == "get_active":
        active_name = get_setting(conn, 'active_address')
        if not active_name:
            return "Активный адрес не задан"
        addr = get_address(conn, active_name)
        if not addr:
            return "Активный адрес не найден в книге"
        return json.dumps(
            {"name": active_name, "address": addr['address'], "coords": addr['coords']},
            ensure_ascii=False
        )

    else:
        return f"Неизвестная операция: {operation}. Доступные: save, save_pending, list, switch, delete, get_active"
