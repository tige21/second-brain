import httpx
from config import YANDEX_GEOCODER_API_KEY, YANDEX_ROUTER_API_KEY, DEFAULT_TRAVEL_MINUTES


async def geocode_address(address: str) -> dict | None:
    """Geocode address to coordinates. Returns {'lat': float, 'lon': float, 'address': str} or None."""
    if not YANDEX_GEOCODER_API_KEY:
        return None
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        'apikey': YANDEX_GEOCODER_API_KEY,
        'geocode': address,
        'format': 'json',
        'results': 1,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    members = data['response']['GeoObjectCollection']['featureMember']
    if not members:
        return None
    obj = members[0]['GeoObject']
    pos = obj['Point']['pos']  # "lon lat"
    lon, lat = map(float, pos.split())
    found_address = obj['metaDataProperty']['GeocoderMetaData']['text']
    return {'lat': lat, 'lon': lon, 'address': found_address}


async def reverse_geocode(lat: float, lon: float) -> str | None:
    """Reverse geocode coordinates to address string."""
    if not YANDEX_GEOCODER_API_KEY:
        return None
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        'apikey': YANDEX_GEOCODER_API_KEY,
        'geocode': f"{lon},{lat}",
        'format': 'json',
        'results': 1,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    members = data['response']['GeoObjectCollection']['featureMember']
    if not members:
        return None
    return members[0]['GeoObject']['metaDataProperty']['GeocoderMetaData']['text']


async def get_travel_time_minutes(
    origin_coords: str,
    destination_coords: str,
    mode: str = "auto",
) -> int:
    """
    Get travel time via Yandex Router.
    origin_coords / destination_coords: "lat,lon"
    Returns minutes. Falls back to DEFAULT_TRAVEL_MINUTES on error.
    """
    if not YANDEX_ROUTER_API_KEY:
        return DEFAULT_TRAVEL_MINUTES
    try:
        origin_lat, origin_lon = origin_coords.split(',')
        dest_lat, dest_lon = destination_coords.split(',')
        url = "https://api.routing.yandex.net/v2/route"
        params = {
            'apikey': YANDEX_ROUTER_API_KEY,
            'waypoints': f"{origin_lat},{origin_lon}|{dest_lat},{dest_lon}",
            'mode': mode,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        duration_seconds = data['route']['legs'][0]['duration']
        return max(1, int(duration_seconds / 60))
    except Exception:
        return DEFAULT_TRAVEL_MINUTES
