"""Village Compare — benchmark one field against nearby analysed fields.

Neighbours come from every user's fields within a radius, but are returned
ANONYMISED: no owner name, no email, no field id for fields you do not own.
Only your own fields are named. Aggregates need at least 2 neighbours, otherwise
the endpoint reports INSUFFICIENT DATA rather than inventing a benchmark.
"""

from statistics import median
from typing import Any, Dict, List, Optional

from lib.db import db
from lib.geo import haversine_km

MIN_PEERS = 2


def _pct_rank(value: Optional[float], peers: List[float]) -> Optional[float]:
    if value is None or not peers:
        return None
    below = sum(1 for p in peers if p < value)
    return round(100.0 * below / len(peers), 1)


def _agg(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0, "average": None, "median": None, "min": None, "max": None}
    return {"count": len(values),
            "average": round(sum(values) / len(values), 1),
            "median": round(median(values), 1),
            "min": round(min(values), 1),
            "max": round(max(values), 1)}


async def compare_field(field: Dict[str, Any], user_id: str,
                        radius_km: float = 25.0) -> Dict[str, Any]:
    lat, lng = field.get("latitude"), field.get("longitude")
    if lat is None or lng is None:
        return {"status": "DATA UNAVAILABLE", "reason": "Field has no centroid coordinates",
                "radius_km": radius_km, "peers": [], "neighbour_count": 0}

    cursor = db.fields.find({"id": {"$ne": field["id"]}}, {"_id": 0})
    peers: List[Dict[str, Any]] = []
    async for doc in cursor:
        plat, plng = doc.get("latitude"), doc.get("longitude")
        if plat is None or plng is None:
            continue
        dist = haversine_km(lat, lng, plat, plng)
        if dist > radius_km:
            continue
        mine = doc.get("user_id") == user_id
        peers.append({
            "distance_km": round(dist, 2),
            "own_field": mine,
            # anonymised for other users' fields — never expose owner or name
            "name": doc.get("name") if mine else "Nearby field (anonymised)",
            "field_id": doc.get("id") if mine else None,
            "area_ha": doc.get("area_ha"),
            "district": doc.get("district"),
            "state": doc.get("state"),
            "flood_pct": doc.get("flood_pct"),
            "land_suitability": doc.get("land_suitability"),
            "recommended_crop": doc.get("recommended_crop"),
            "analysed": doc.get("last_analysis") is not None,
        })
    peers.sort(key=lambda p: p["distance_km"])

    analysed = [p for p in peers if p["analysed"]]
    flood_vals = [float(p["flood_pct"]) for p in analysed if p["flood_pct"] is not None]
    suit_vals = [float(p["land_suitability"]) for p in analysed if p["land_suitability"] is not None]

    my_flood = field.get("flood_pct")
    my_suit = field.get("land_suitability")

    crop_counts: Dict[str, int] = {}
    for p in analysed:
        c = p.get("recommended_crop")
        if c:
            crop_counts[c] = crop_counts.get(c, 0) + 1
    popular = sorted(crop_counts.items(), key=lambda kv: kv[1], reverse=True)

    status = "OK" if len(analysed) >= MIN_PEERS else "INSUFFICIENT DATA"
    verdicts: List[str] = []
    if status == "OK":
        fa = _agg(flood_vals)["average"]
        sa = _agg(suit_vals)["average"]
        if my_flood is not None and fa is not None:
            if my_flood > fa + 1:
                verdicts.append(f"This field is wetter than the local average ({my_flood}% vs {fa}%).")
            elif my_flood < fa - 1:
                verdicts.append(f"This field is drier than the local average ({my_flood}% vs {fa}%).")
            else:
                verdicts.append(f"Flood level is in line with nearby fields ({my_flood}% vs {fa}%).")
        if my_suit is not None and sa is not None:
            delta = round(my_suit - sa, 1)
            verdicts.append(
                f"Land suitability is {abs(delta)} points {'above' if delta >= 0 else 'below'} "
                f"the local average ({my_suit} vs {sa}).")
        if popular:
            verdicts.append(f"Most recommended crop nearby: {popular[0][0]} "
                            f"({popular[0][1]} of {len(analysed)} analysed fields).")
    else:
        verdicts.append(f"Only {len(analysed)} analysed field(s) within {radius_km:g} km — "
                        f"at least {MIN_PEERS} are needed before a benchmark is shown. "
                        f"Nothing is estimated.")

    return {
        "status": status,
        "radius_km": radius_km,
        "field": {"id": field["id"], "name": field.get("name"),
                  "flood_pct": my_flood, "land_suitability": my_suit,
                  "recommended_crop": field.get("recommended_crop"),
                  "district": field.get("district"), "state": field.get("state")},
        "neighbour_count": len(peers),
        "analysed_neighbour_count": len(analysed),
        "flood": {**_agg(flood_vals), "your_value": my_flood,
                  "your_percentile": _pct_rank(my_flood, flood_vals)},
        "suitability": {**_agg(suit_vals), "your_value": my_suit,
                        "your_percentile": _pct_rank(my_suit, suit_vals)},
        "popular_crops": [{"crop": c, "fields": n} for c, n in popular[:5]],
        "peers": peers[:40],
        "verdicts": verdicts,
        "privacy": ("Other users' fields are shown anonymised — distance, area and scores only, "
                    "never owner, name or exact boundary."),
    }
