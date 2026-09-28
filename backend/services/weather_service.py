"""Weather + rainfall intelligence — Open-Meteo (keyless, real data).

Forecast API for current conditions; Archive API for recent daily rainfall used as
supporting flood evidence. Never used alone to declare a flood.
"""

from datetime import date, timedelta
from typing import Any, Dict

from lib import ext_http

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


async def current_weather(lat: float, lng: float) -> Dict[str, Any]:
    params = {
        "latitude": lat, "longitude": lng,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "forecast_days": 3, "timezone": "auto",
    }
    return await ext_http.request("GET", FORECAST_URL, source="weather", params=params)


async def recent_rainfall(lat: float, lng: float, days: int = 30) -> Dict[str, Any]:
    """Daily precipitation totals for the last `days` days (archive, ~2-5 day lag)."""
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=days)
    params = {
        "latitude": lat, "longitude": lng,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "precipitation_sum,rain_sum", "timezone": "auto",
    }
    data = await ext_http.request("GET", ARCHIVE_URL, source="weather_archive", params=params)
    daily = (data or {}).get("daily", {})
    rains = [float(v) for v in (daily.get("rain_sum") or []) if v is not None]
    total_mm = round(sum(rains), 1)
    last7 = round(sum(rains[-7:]), 1) if len(rains) >= 7 else total_mm
    wet_days = sum(1 for r in rains if r >= 10.0)
    max_day = round(max(rains), 1) if rains else 0.0
    return {
        "period_days": days, "start_date": start.isoformat(), "end_date": end.isoformat(),
        "total_mm": total_mm, "last_7_days_mm": last7, "wet_days_10mm": wet_days,
        "max_daily_mm": max_day, "daily": daily.get("rain_sum") or [],
        "dates": daily.get("time") or [],
    }


def rainfall_verdict(recent: Dict[str, Any]) -> Dict[str, Any]:
    """Plain-language supporting evidence derived from archive rainfall."""
    if not recent:
        return {"level": "unavailable", "statement": "Rainfall data unavailable — flood plausibility could not be cross-checked."}
    last7 = recent.get("last_7_days_mm", 0) or 0
    maxd = recent.get("max_daily_mm", 0) or 0
    if last7 >= 100 or maxd >= 60:
        level, statement = "high", ("Heavy recent rainfall strongly increases the plausibility of "
                                    "temporary surface-water expansion.")
    elif last7 >= 35 or maxd >= 25:
        level, statement = "elevated", ("Recent rainfall increased the plausibility of temporary "
                                        "surface-water expansion.")
    elif last7 > 0:
        level, statement = "low", "Only light recent rainfall — widespread new flooding is less plausible."
    else:
        level, statement = "dry", "No meaningful rainfall recorded recently — detected water would need another explanation."
    return {"level": level, "statement": statement, "last_7_days_mm": last7, "max_daily_mm": maxd}
