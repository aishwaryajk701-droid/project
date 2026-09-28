"""OpenStreetMap context via the Overpass API (keyless, real data).

Used for river/lake/reservoir verification and building/road/built-up verification
around a field. Attributed to OpenStreetMap contributors (ODbL).
"""

from typing import Any, Dict, List

from lib import ext_http

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# keep bboxes small — Overpass usage policy


def _bbox(bbox: List[float]) -> str:
    return f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"  # s,w,n,e


QUERY_TMPL = """[out:json][timeout:25];
(
  way["waterway"]({b});
  relation["waterway"]({b});
  way["natural"="water"]({b});
  relation["natural"="water"]({b});
  way["landuse"="reservoir"]({b});
  way["building"]({b});
  way["highway"]({b});
  way["landuse"]({b});
  relation["landuse"]({b});
);
out center tags;
"""


async def fetch_osm_context(bbox: List[float]) -> Dict[str, Any]:
    q = QUERY_TMPL.format(b=_bbox(bbox))
    data = await ext_http.request("POST", OVERPASS_URL, source="osm",
                                  content=q.encode("utf-8"),
                                  headers={"Content-Type": "text/plain"},
                                  cache_payload={"q": q})
    elements = (data or {}).get("elements", [])
    waterways: List[Dict[str, Any]] = []
    water_bodies: List[Dict[str, Any]] = []
    buildings: List[Dict[str, Any]] = []
    roads = 0
    landuse: Dict[str, int] = {}
    for el in elements:
        tags = el.get("tags") or {}
        center = el.get("center") or {}
        lat = el.get("lat") or center.get("lat")
        lng = el.get("lon") or center.get("lon")
        if tags.get("waterway"):
            waterways.append({"type": tags["waterway"], "name": tags.get("name"),
                              "lat": lat, "lng": lng})
        elif tags.get("natural") == "water" or tags.get("landuse") == "reservoir":
            water_bodies.append({"kind": tags.get("water") or tags.get("landuse"),
                                 "name": tags.get("name"), "lat": lat, "lng": lng})
        elif tags.get("building") is not None:
            buildings.append({"lat": lat, "lng": lng})
        elif tags.get("highway"):
            roads += 1
        elif tags.get("landuse"):
            lu = tags["landuse"]
            landuse[lu] = landuse.get(lu, 0) + 1
    return {
        "waterways": waterways[:40], "water_bodies": water_bodies[:40],
        "building_count": len(buildings), "buildings_sample": buildings[:25],
        "road_count": roads, "landuse_counts": landuse,
        "source": "OpenStreetMap (Overpass API) — © OpenStreetMap contributors",
    }


def water_context(context: Dict[str, Any] | None) -> Dict[str, Any]:
    """Summarise nearby rivers/lakes/canals for the water-verification step."""
    if not context:
        return {"nearby_waterways": 0, "nearby_water_bodies": 0,
                "verdict": "unknown", "note": "OpenStreetMap context unavailable."}
    nw, nb = len(context.get("waterways") or []), len(context.get("water_bodies") or [])
    if nw or nb:
        kinds = sorted({w["type"] for w in (context.get("waterways") or []) if w.get("type")})
        verdict = "water_features_present"
        note = (f"{nw} mapped waterway feature(s) and {nb} water body(ies) near the field "
                f"({', '.join(kinds[:4]) or 'unclassified'}); detected water may relate to these.")
    else:
        verdict = "no_mapped_water"
        note = "No mapped river/lake/canal features within the field's bounding box."
    return {"nearby_waterways": nw, "nearby_water_bodies": nb, "verdict": verdict, "note": note,
            "names": [w.get("name") for w in (context.get("waterways") or []) if w.get("name")][:5]}


def builtup_context(context: Dict[str, Any] | None) -> Dict[str, Any]:
    if not context:
        return {"building_count": None, "road_count": None, "verdict": "unknown",
                "note": "OpenStreetMap context unavailable — built-up verification not possible."}
    b = context.get("building_count") or 0
    r = context.get("road_count") or 0
    if b >= 10 or r >= 10:
        verdict, note = "builtup_present", (f"{b} building(s) and {r} road segment(s) mapped in the "
                                            f"area — water here is treated as built-up context, not agricultural flood.")
    elif b or r:
        verdict, note = "sparse_builtup", f"{b} building(s) and {r} road segment(s) mapped nearby."
    else:
        verdict, note = "no_builtup", "No mapped buildings or roads in the field's bounding box."
    return {"building_count": b, "road_count": r, "verdict": verdict, "note": note}


def cropland_context(context: Dict[str, Any] | None) -> Dict[str, Any]:
    """OSM landuse as a keyless cropland signal (used when WorldCover is unavailable)."""
    if not context:
        return None
    counts = context.get("landuse_counts") or {}
    ag = sum(v for k, v in counts.items() if k in ("farmland", "orchard", "vineyard", "plant_nursery", "greenhouse_horticulture"))
    total = sum(counts.values()) or 1
    return {"agricultural_polygons": ag, "total_landuse_polygons": total,
            "counts": counts, "source": "OpenStreetMap landuse"}
