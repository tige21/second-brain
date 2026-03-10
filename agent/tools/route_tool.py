import sqlite3
from langchain_core.tools import tool
from services.osrm import calculate_route as _osrm_route
from services.yandex_geocoder import geocode_address
from db.database import get_conn
from db.models import get_setting, get_address
from agent.context import get_current_chat_id


def _resolve_coords_from_db(value: str, conn: sqlite3.Connection, chat_id: int) -> str | None:
    """Check address book and raw coords. Returns 'lat,lon' or None."""
    parts = value.replace(' ', '').split(',')
    if len(parts) == 2:
        try:
            float(parts[0])
            float(parts[1])
            return value.replace(' ', '')
        except ValueError:
            pass
    addr = get_address(conn, chat_id, value.lower())
    if addr:
        return addr['coords']
    return None


async def _resolve_to_coords(value: str, conn: sqlite3.Connection, chat_id: int) -> str | None:
    """Resolve address to 'lat,lon': address book → Nominatim geocoding."""
    coords = _resolve_coords_from_db(value, conn, chat_id)
    if coords:
        return coords
    geo = await geocode_address(value)
    if geo:
        return f"{geo['lat']},{geo['lon']}"
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
        chat_id = get_current_chat_id()
        origin_coords = await _resolve_to_coords(origin, conn, chat_id)
        dest_coords = await _resolve_to_coords(destination, conn, chat_id)

        if not origin_coords:
            return f"Не удалось определить координаты для адреса '{origin}'. Попробуй указать полный адрес с городом."
        if not dest_coords:
            return f"Не удалось определить координаты для адреса '{destination}'. Попробуй указать полный адрес с городом."

        result = await _osrm_route(origin_coords, dest_coords, mode)

        if "error" in result:
            return f"❌ Ошибка маршрута ({mode}): {result['error']}"

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
        return f"❌ Ошибка при расчёте маршрута: {e}"
