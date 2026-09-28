"""Terrain engine — Copernicus DEM GLO-90 via the Open-Meteo elevation API (keyless, real data).

A field bbox is sampled on a grid (≤100 points per request); elevation statistics and an
approximate slope are derived from the real sample. Terrain is supporting evidence only.
"""

from typing import Any, Dict, List

from lib import ext_http
from lib.geo import sample_grid

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
DEM_SOURCE = "Copernicus DEM GLO-90 (via Open-Meteo elevation API)"
DEM_RESOLUTION = "approximately 90 m"


async def fetch_terrain(bbox: List[float]) -> Dict[str, Any]:
    pts = sample_grid(bbox, side=8)  # 64 points ≤ 100-point limit
    lats = ",".join(str(p[0]) for p in pts)
    lngs = ",".join(str(p[1]) for p in pts)
    data = await ext_http.request("GET", ELEVATION_URL, source="elevation",
                                  params={"latitude": lats, "longitude": lngs})
    dem = (data.get("elevation") or data.get("dem")) if isinstance(data, dict) else None
    elevations = [float(e) for e in (dem or []) if e is not None]
    if len(elevations) < 4:
        raise RuntimeError("Elevation API returned too few points")

    n = int(len(elevations) ** 0.5)
    elev_range = max(elevations) - min(elevations)
    mean_elev = sum(elevations) / len(elevations)

    # slope from neighbouring grid cells (rise over run in metres, cell ≈ bbox_size / n)
    cell_km = max(_bbox_span_km(bbox) / max(n - 1, 1), 1e-6)
    slopes: List[float] = []
    low_cells = 0
    for i in range(n):
        for j in range(n):
            v = elevations[i * n + j]
            if v < mean_elev:
                low_cells += 1
            neigh: List[float] = []
            for di, dj in ((0, 1), (1, 0)):
                ii, jj = i + di, j + dj
                if ii < n and jj < n:
                    neigh.append(elevations[ii * n + jj])
            if neigh:
                drop = max(abs(v - x) for x in neigh)
                slopes.append(drop / max(cell_km * 1000.0, 1e-6) * 100.0)  # % grade
    slopes.sort()
    median_slope = slopes[len(slopes) // 2] if slopes else 0.0
    low_lying_pct = round(100.0 * low_cells / len(elevations), 1)

    if elev_range <= 5:
        risk = "low"
    elif elev_range <= 20 or median_slope < 1.5:
        risk = "moderate"
    else:
        risk = "high"
    return {
        "elevation_min_m": round(min(elevations), 1),
        "elevation_max_m": round(max(elevations), 1),
        "elevation_mean_m": round(mean_elev, 1),
        "elevation_range_m": round(elev_range, 1),
        "slope_median_pct": round(median_slope, 2),
        "low_lying_pct": low_lying_pct,
        "terrain_risk": risk,
        "sample_points": len(elevations),
        "source": DEM_SOURCE,
        "resolution": DEM_RESOLUTION,
    }


def _bbox_span_km(bbox: List[float]) -> float:
    import math
    lat_span = abs(bbox[3] - bbox[1])
    lng_span = abs(bbox[2] - bbox[0]) * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    return max(lat_span, lng_span) * 111.32


def terrain_factor(terrain: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not terrain:
        return None
    risk = terrain.get("terrain_risk")
    return {"score": {"low": 90.0, "moderate": 70.0, "high": 45.0}.get(risk, 70.0),
            "risk": risk}
