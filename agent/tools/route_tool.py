import sqlite3
from langchain_core.tools import tool
from services.osrm import calculate_route as _osrm_route
from db.database import get_conn
from db.models import get_setting, get_address


def _resolve_to_coords(value: str, conn: sqlite3.Connection) -> str | None:
    """Resolve address name or 'lat,lon' string to normalised 'lat,lon'."""
    # Already coordinates?
    parts = value.replace(' ', '').split(',')
    if len(parts) == 2:
        try:
            float(parts[0])
            float(parts[1])
            return value.replace(' ', '')
        except ValueError:
            pass
    # Named address in address book?
    addr = get_address(conn, value.lower())
    if addr:
        return addr['coords']
    # Active address fallback
    active_name = get_setting(conn, 'active_address')
    if active_name:
        active = get_address(conn, active_name)
        if active:
            return active['coords']
    return None


@tool
async def calculate_route(
    origin: str,
    destination: str,
    mode: str = "driving",
) -> str:
    """
    Calculate route between two points using OSRM (free routing).
    origin: address name from address book (e.g. "дом"), coordinates "lat,lon", or text address.
    destination: same format as origin.
    mode: "driving" (car) or "masstransit" (public transport, also uses car routing).
    Call this TWICE for each route request: once with mode="driving", once with mode="masstransit".
    """
    try:
        conn = get_conn()
        origin_coords = _resolve_to_coords(origin, conn)
        dest_coords = _resolve_to_coords(destination, conn)

        if not origin_coords:
            return f"Не удалось определить координаты для '{origin}'. Добавь адрес в адресную книгу."
        if not dest_coords:
            return f"Не удалось определить координаты для '{destination}'."

        result = await _osrm_route(origin_coords, dest_coords, mode)

        if "error" in result:
            return f"Ошибка маршрута ({mode}): {result['error']}"

        duration: int = result['duration_minutes']
        distance: float = result['distance_km']

        if duration > 60:
            indicator = "🔴"
        elif duration > 30:
            indicator = "🟡"
        else:
            indicator = "🟢"

        mode_label = {
            "driving": "🚗 На машине",
            "masstransit": "🚌 Общественный",
            "walking": "🚶 Пешком",
            "cycling": "🚲 Велосипед",
        }.get(mode, mode)

        return f"{indicator} {mode_label}: {duration} мин, {distance} км"
    except Exception as e:
        return f"Ошибка при расчёте маршрута: {e}"
