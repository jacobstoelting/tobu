import requests
from datetime import datetime, timedelta

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → human-readable summary
_WMO_CODES = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "icy fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def get_run_weather(lat, lon, start_time_local_str, duration_min):
    """Fetch historical weather for the run's time window.

    Returns a dict with averaged conditions, or None if lat/lon unavailable or API fails.
    """
    if not lat or not lon:
        return None

    try:
        start_dt = datetime.strptime(start_time_local_str[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None

    run_date = start_dt.strftime("%Y-%m-%d")
    start_hour = start_dt.hour
    duration_min = duration_min or 60
    end_hour = min(23, int((start_dt + timedelta(minutes=duration_min)).hour))

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": run_date,
        "end_date": run_date,
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,uv_index,precipitation",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }

    try:
        resp = requests.get(ARCHIVE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    hourly = data.get("hourly", {})
    hours = hourly.get("time", [])

    # Find indices that fall within the run window
    indices = [
        i for i, t in enumerate(hours)
        if start_hour <= datetime.fromisoformat(t).hour <= max(start_hour, end_hour)
    ]
    if not indices:
        indices = [start_hour] if start_hour < len(hours) else [0]

    def avg(key):
        vals = [hourly[key][i] for i in indices if hourly.get(key) and hourly[key][i] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    altitude_m = data.get("elevation")
    altitude_ft = round(altitude_m * 3.28084) if altitude_m is not None else None

    return {
        "temp_f": avg("temperature_2m"),
        "feels_like_f": avg("apparent_temperature"),
        "humidity_pct": avg("relative_humidity_2m"),
        "wind_mph": avg("wind_speed_10m"),
        "uv_index": avg("uv_index"),
        "precipitation_in": avg("precipitation"),
        "altitude_ft": altitude_ft,
    }


def get_forecast(lat, lon):
    """Fetch a 3-day weather forecast.

    Returns a list of up to 3 dicts, or [] on failure.
    """
    if not lat or not lon:
        return []

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,uv_index_max,weathercode",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "forecast_days": 3,
        "timezone": "auto",
    }

    try:
        resp = requests.get(FORECAST_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    result = []

    for i, date in enumerate(dates[:3]):
        code = (daily.get("weathercode") or [None] * (i + 1))[i]
        result.append({
            "date": date,
            "high_f": (daily.get("temperature_2m_max") or [None] * (i + 1))[i],
            "low_f": (daily.get("temperature_2m_min") or [None] * (i + 1))[i],
            "wind_mph": (daily.get("wind_speed_10m_max") or [None] * (i + 1))[i],
            "uv_index": (daily.get("uv_index_max") or [None] * (i + 1))[i],
            "precip_in": (daily.get("precipitation_sum") or [None] * (i + 1))[i],
            "summary": _WMO_CODES.get(code, "unknown") if code is not None else "unknown",
        })

    return result
