"""Soil intelligence — ISRIC SoilGrids v2.0 REST (keyless, real data, ~250 m resolution).

Values arrive in SoilGrids' internal units and are converted with the published
factors; the source resolution is always reported back to the UI.
"""

from typing import Any, Dict

from lib import ext_http

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
RESOLUTION = "approximately 250 m (ISRIC SoilGrids 2.0)"
PROPERTIES = ["phh2o", "clay", "sand", "silt", "soc", "bdod", "cec", "nitrogen"]

# conversion factors from SoilGrids mapped units -> conventional units
FACTORS = {
    "phh2o": ("pH (H2O)", 0.1, "pH"),
    "clay": ("Clay", 0.1, "% wt"),
    "sand": ("Sand", 0.1, "% wt"),
    "silt": ("Silt", 0.1, "% wt"),
    "soc": ("Organic carbon", 0.1, "g/kg"),
    "bdod": ("Bulk density", 0.01, "kg/dm³"),
    "cec": ("CEC", 0.1, "cmol(+)/kg"),
    "nitrogen": ("Total nitrogen", 0.1, "g/kg"),
}


async def fetch_soil(lat: float, lng: float) -> Dict[str, Any]:
    params: Dict[str, Any] = {"lon": lng, "lat": lat, "depth": "0-5cm", "value": "mean"}
    for p in PROPERTIES:
        params.setdefault("property", []).append(p)

    data = await ext_http.request("GET", SOILGRIDS_URL, source="soil", params=params)
    layers = ((data or {}).get("properties") or {}).get("layers") or []
    out: Dict[str, Any] = {}
    for layer in layers:
        name = layer.get("name")
        if name not in FACTORS:
            continue
        label, factor, unit = FACTORS[name]
        depths = layer.get("depths") or []
        raw = None
        if depths:
            raw = ((depths[0] or {}).get("values") or {}).get("mean")
        if raw is None:
            continue
        out[name] = {"label": label, "value": round(float(raw) * factor, 2), "unit": unit}
    if not out:
        raise RuntimeError("SoilGrids returned no usable layers")
    texture = _texture_class(out.get("clay", {}).get("value"), out.get("sand", {}).get("value"))
    return {
        "properties": out,
        "texture_class": texture,
        "source": "ISRIC SoilGrids 2.0",
        "resolution": RESOLUTION,
        "depth": "0-5 cm",
    }


def _texture_class(clay: Any, sand: Any) -> Dict[str, Any] | None:
    if clay is None or sand is None:
        return None
    c, s = float(clay), float(sand)
    if c >= 35:
        name = "Clay / clay-rich"
    elif c >= 20 and s <= 45:
        name = "Loam"
    elif s >= 70:
        name = "Sandy"
    elif c < 20 and s >= 45:
        name = "Sandy loam"
    else:
        name = "Fine loamy"
    return {"class": name, "clay_pct": c, "sand_pct": s}


def texture_scores(soil: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """0-100 factor scores derived from real SoilGrids values (None → not scored)."""
    if not soil or not soil.get("properties"):
        return None
    props = soil["properties"]
    ph = (props.get("phh2o") or {}).get("value")
    oc = (props.get("soc") or {}).get("value")

    def ph_score(v: float | None) -> float | None:
        if v is None:
            return None
        if 5.5 <= v <= 7.2:
            return 95.0
        if 5.0 <= v < 5.5 or 7.2 < v <= 7.8:
            return 80.0
        if 4.5 <= v < 5.0 or 7.8 < v <= 8.5:
            return 60.0
        return 40.0

    def oc_score(v: float | None) -> float | None:
        if v is None:
            return None
        # SOC g/kg: 5 -> poor, 10 -> fair, 20+ -> good
        return max(20.0, min(95.0, 20.0 + v * 3.5))

    return {"ph": ph_score(ph), "organic_carbon": oc_score(oc)}
