import httpx

OSRM_BASE_URL = "https://router.project-osrm.org"


async def calculate_route(
    origin_coords: str,
    destination_coords: str,
    mode: str = "driving",
) -> dict:
    """
    Calculate route via OSRM (free, open source).
    origin_coords / destination_coords: "lat,lon"
    mode: "driving" | "walking" | "cycling" | "masstransit" (mapped to car)
    Returns: {'duration_minutes': int, 'distance_km': float, 'mode': str}
    """
    try:
        origin_lat, origin_lon = origin_coords.split(',')
        dest_lat, dest_lon = destination_coords.split(',')

        profile_map = {
            "driving": "car",
            "walking": "foot",
            "cycling": "bike",
            "masstransit": "car",
        }
        profile = profile_map.get(mode, "car")

        coords = f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        url = f"{OSRM_BASE_URL}/route/v1/{profile}/{coords}"
        params = {"overview": "false"}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get('code') != 'Ok' or not data.get('routes'):
            return {"error": "No route found", "mode": mode}

        route = data['routes'][0]
        duration_minutes = max(1, int(route['duration'] / 60))
        distance_km = round(route['distance'] / 1000, 1)

        return {
            "duration_minutes": duration_minutes,
            "distance_km": distance_km,
            "mode": mode,
        }
    except Exception as e:
        return {"error": str(e), "mode": mode}
