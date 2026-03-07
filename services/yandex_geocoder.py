"""
Geocoding via Nominatim (OpenStreetMap) — free, no API key required.
Travel time via OSRM — free, no API key required.
"""
import httpx
from config import DEFAULT_TRAVEL_MINUTES

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
# Required by Nominatim Terms of Use: https://operations.osmfoundation.org/policies/nominatim/
_HEADERS = {"User-Agent": "SecondBrainBot/1.0 (personal assistant)"}


async def geocode_address(address: str) -> dict | None:
    """
    Geocode a text address to coordinates using Nominatim.
    Returns {'lat': float, 'lon': float, 'address': str} or None if not found.
    """
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            resp = await client.get(
                f"{NOMINATIM_URL}/search",
                params={"q": address, "format": "json", "limit": 1},
            )
            resp.raise_for_status()
            results = resp.json()
        if not results:
            return None
        r = results[0]
        return {
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "address": r.get("display_name", address),
        }
    except Exception:
        return None


async def reverse_geocode(lat: float, lon: float) -> str | None:
    """
    Reverse geocode coordinates to a human-readable address using Nominatim.
    Returns address string or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            resp = await client.get(
                f"{NOMINATIM_URL}/reverse",
                params={"lat": lat, "lon": lon, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("display_name")
    except Exception:
        return None


async def get_travel_time_minutes(
    origin_coords: str,
    destination_coords: str,
    mode: str = "driving",
) -> int:
    """
    Calculate travel time in minutes using OSRM (free, open source routing).
    Falls back to DEFAULT_TRAVEL_MINUTES on any error.
    """
    from services.osrm import calculate_route
    result = await calculate_route(origin_coords, destination_coords, mode)
    if "error" in result:
        return DEFAULT_TRAVEL_MINUTES
    return int(result.get("duration_minutes", DEFAULT_TRAVEL_MINUTES))
