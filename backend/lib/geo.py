"""Geospatial helpers: polygon validation, area, bbox, grids. Pure functions, no I/O."""

import math
from typing import List, Tuple

R_EARTH = 6378137.0
MAX_POLY_POINTS = 400
MAX_AREA_HA = 100_000.0  # 1000 km2 sanity cap


class PolygonError(ValueError):
    pass


def validate_polygon(coords: List[List[float]]) -> None:
    """coords: [[lng, lat], ...] optionally closed. Raises PolygonError with a human message."""
    if coords is None or len(coords) < 3:
        raise PolygonError("Polygon needs at least 3 points")
    if len(coords) > MAX_POLY_POINTS:
        raise PolygonError(f"Polygon too complex (max {MAX_POLY_POINTS} vertices)")
    for c in coords:
        if not isinstance(c, (list, tuple)) or len(c) < 2:
            raise PolygonError("Each vertex must be [lng, lat]")
        lng, lat = float(c[0]), float(c[1])
        if not (-180.0 <= lng <= 180.0) or not (-90.0 <= lat <= 90.0):
            raise PolygonError(f"Vertex out of bounds: [{lng}, {lat}]")
    # dedupe consecutive identical points (and closure point) for the area check
    pts: List[Tuple[float, float]] = [(float(c[0]), float(c[1])) for c in coords]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise PolygonError("Polygon degenerates to fewer than 3 unique points")
    if polygon_area_ha([list(p) for p in pts]) <= 0:
        raise PolygonError("Polygon has zero area")
    area = polygon_area_ha([list(p) for p in pts])
    if area > MAX_AREA_HA:
        raise PolygonError(f"Polygon too large ({area:.0f} ha; max {MAX_AREA_HA:.0f} ha)")


def bbox_from_polygon(coords: List[List[float]]) -> List[float]:
    lngs = [float(c[0]) for c in coords]
    lats = [float(c[1]) for c in coords]
    return [min(lngs), min(lats), max(lngs), max(lats)]


def polygon_area_ha(coords: List[List[float]]) -> float:
    """Area in hectares via the shoelace formula on an equirectangular projection."""
    pts = [(float(c[0]), float(c[1])) for c in coords]
    if len(pts) >= 3 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return 0.0
    lat_avg = sum(p[1] for p in pts) / len(pts)
    xs = [math.radians(p[0]) * R_EARTH * math.cos(math.radians(lat_avg)) for p in pts]
    ys = [math.radians(p[1]) * R_EARTH for p in pts]
    area = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        area += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(area) / 2.0 / 10_000.0


def polygon_centroid(coords: List[List[float]]) -> Tuple[float, float]:
    pts = [(float(c[0]), float(c[1])) for c in coords]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    lat = sum(p[1] for p in pts) / len(pts)
    lng = sum(p[0] for p in pts) / len(pts)
    return lng, lat


def point_in_polygon(lng: float, lat: float, coords: List[List[float]]) -> bool:
    """Ray-casting inclusion test."""
    pts = [(float(c[0]), float(c[1])) for c in coords]
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < x_cross:
                inside = not inside
        j = i
    return inside


def sample_grid(bbox: List[float], side: int = 8) -> List[Tuple[float, float]]:
    """Up to side*side (lat, lng) points inside the bbox, centres of a regular grid.
    Used for elevation / land-cover sampling; capped at 100 points (Open-Meteo limit)."""
    lng_min, lat_min, lng_max, lat_max = bbox
    n = max(2, min(side, 10))
    pts: List[Tuple[float, float]] = []
    for i in range(n):
        for j in range(n):
            lat = lat_min + (i + 0.5) * (lat_max - lat_min) / n
            lng = lng_min + (j + 0.5) * (lng_max - lng_min) / n
            pts.append((round(lat, 6), round(lng, 6)))
    return pts[:100]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
