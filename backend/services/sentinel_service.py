"""Sentinel Hub integration (OAuth client-credentials) — OPTIONAL.

When SENTINEL_HUB_CLIENT_ID/_SECRET are absent every function returns None and the
pipeline degrades to keyless sources / demo mode. Never fabricates imagery.
"""

import io
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
import numpy as np

from lib import ext_http

logger = logging.getLogger("agriguard.sentinel")

SH_BASE_URL = "https://services.sentinel-hub.com"
_token_cache: Dict[str, Any] = {"token": None, "exp": 0}


def configured() -> bool:
    import os
    return bool(os.environ.get("SENTINEL_HUB_CLIENT_ID", "").strip()
                and os.environ.get("SENTINEL_HUB_CLIENT_SECRET", "").strip())


async def get_token() -> Optional[str]:
    import os
    if not configured():
        return None
    if _token_cache["token"] and _token_cache["exp"] > time.time() + 30:
        return _token_cache["token"]
    cid = os.environ["SENTINEL_HUB_CLIENT_ID"].strip()
    secret = os.environ["SENTINEL_HUB_CLIENT_SECRET"].strip()
    try:
        r = await ext_http.get_client().post(
            f"{SH_BASE_URL}/auth/realms/main/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            logger.error("Sentinel Hub auth failed: %s %s", r.status_code, r.text[:200])
            return None
        j = r.json()
        _token_cache["token"] = j["access_token"]
        _token_cache["exp"] = time.time() + int(j.get("expires_in", 3500))
        return j["access_token"]
    except Exception as exc:
        logger.error("Sentinel Hub token error: %s", exc)
        return None


# Evalscripts -------------------------------------------------------------

SCRIPT_S1_BANDS = """//VERSION=3
function setup() {
  return { input: ["VV","VH","dataMask"], output: { bands: 3, sampleType: "FLOAT32" } };
}
function evaluatePixel(s) {
  if (s.dataMask === 0) return [NaN, NaN, 0];
  return [s.VV, s.VH, 1];
}"""

SCRIPT_S2_BANDS = """//VERSION=3
function setup() {
  return { input: ["B02","B03","B04","B08","B11","SCL","dataMask"], output: { bands: 7, sampleType: "FLOAT32" } };
}
function evaluatePixel(s) {
  if (s.dataMask === 0) return [NaN,NaN,NaN,NaN,NaN,NaN,0];
  return [s.B02, s.B03, s.B04, s.B08, s.B11, s.SCL, 1];
}"""

SCRIPT_S1_TRUE = """//VERSION=3
function setup() { return { input: ["VV","VH","dataMask"], output: { bands: 4, sampleType: "UINT8" } }; }
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0,0,0,0];
  var g1 = Math.min(255, Math.max(0, Math.round(Math.sqrt(s.VV) * 900)));
  var g2 = Math.min(255, Math.max(0, Math.round(Math.sqrt(s.VH) * 900)));
  return [g1, g2, g1, 255];
}"""

SCRIPT_S2_TRUE = """//VERSION=3
function setup() { return { input: ["B02","B03","B04","dataMask"], output: { bands: 4, sampleType: "UINT8" } }; }
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0,0,0,0];
  var g = 2.5;
  return [Math.min(255, s.B04 * 255 * g), Math.min(255, s.B03 * 255 * g), Math.min(255, s.B02 * 255 * g), 255];
}"""


async def catalog_search(bbox: List[float], date_from: str, date_to: str,
                         collection: str = "sentinel-1-grd", limit: int = 30,
                         max_cloud: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
    token = await get_token()
    if not token:
        return None
    body: Dict[str, Any] = {
        "bbox": bbox,
        "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
        "collections": [collection],
        "limit": limit,
    }
    if max_cloud is not None:
        body["query"] = {"eo:cloud_cover": {"lt": max_cloud}}
    try:
        r = await ext_http.get_client().post(
            f"{SH_BASE_URL}/api/v1/catalog/1.0.0/search",
            headers={"Authorization": f"Bearer {token}"}, json=body)
        if r.status_code != 200:
            logger.error("SH catalog failed %s %s", r.status_code, r.text[:200])
            return None
        return r.json().get("features", [])
    except Exception as exc:
        logger.error("SH catalog error: %s", exc)
        return None


def _process_payload(bbox: List[float], date_from: str, date_to: str, evalscript: str,
                     collection: str, width: int = 128, mime: str = "image/tiff",
                     mosaicking: str = "leastRecent", max_cloud: Optional[int] = None) -> Dict[str, Any]:
    data_block: Dict[str, Any] = {
        "type": collection,
        "dataFilter": {"timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
                       "mosaickingOrder": mosaicking},
    }
    if max_cloud is not None:
        data_block["dataFilter"]["maxCloudCoverage"] = max_cloud
    return {
        "input": {
            "bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [data_block],
        },
        "output": {"width": width, "height": width,
                   "responses": [{"identifier": "default", "format": {"type": mime}}]},
        "evalscript": evalscript,
    }


async def process_raw(bbox: List[float], date_from: str, date_to: str, evalscript: str,
                      collection: str, width: int = 128, mime: str = "image/tiff",
                      mosaicking: str = "leastRecent", max_cloud: Optional[int] = None,
                      ttl: Optional[int] = None) -> Optional[bytes]:
    """Returns raw response bytes, or None (unconfigured / no data / upstream failure)."""
    token = await get_token()
    if not token:
        return None
    payload = _process_payload(bbox, date_from, date_to, evalscript, collection, width, mime,
                               mosaicking, max_cloud)
    try:
        import json

        r = await ext_http.get_client().post(
            f"{SH_BASE_URL}/api/v1/process",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "Accept": mime},
            json=payload)
        if r.status_code != 200:
            logger.error("SH process failed %s %s", r.status_code, r.text[:300])
            return None
        return r.content
    except Exception as exc:
        logger.error("SH process error: %s", exc)
        return None


async def process_bands_tiff(bbox: List[float], date_from: str, date_to: str,
                             collection: str, width: int = 128,
                             mosaicking: str = "leastRecent",
                             max_cloud: Optional[int] = None) -> Optional[np.ndarray]:
    """S1 (VV,VH,mask) or S2 (B02,B03,B04,B08,B11,SCL,mask) as a float32 HxWxB array."""
    script = SCRIPT_S1_BANDS if collection.startswith("sentinel-1") else SCRIPT_S2_BANDS
    raw = await process_raw(bbox, date_from, date_to, script, collection, width=width,
                            mime="image/tiff", mosaicking=mosaicking, max_cloud=max_cloud)
    if raw is None:
        return None
    try:
        import tifffile
        arr = tifffile.imread(io.BytesIO(raw))
        if arr.ndim == 2:
            arr = arr[..., np.newaxis]
        return np.asarray(arr, dtype=np.float32)
    except Exception as exc:
        logger.error("tiff parse failed: %s", exc)
        return None


async def process_true_color_png(bbox: List[float], date_from: str, date_to: str,
                                 collection: str = "sentinel-2-l2a", width: int = 512,
                                 mosaicking: str = "leastCC",
                                 max_cloud: Optional[int] = 40) -> Optional[bytes]:
    script = SCRIPT_S2_TRUE if collection.startswith("sentinel-2") else SCRIPT_S1_TRUE
    return await process_raw(bbox, date_from, date_to, script, collection, width=width,
                             mime="image/png", mosaicking=mosaicking, max_cloud=max_cloud)


# --- Land cover via WorldCover WMS (keyless, real ESA WorldCover 2021) ---

WORLDCOVER_WMS = "https://services.terrascope.be/wms/v2"
WC_CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland",
    50: "Built-up", 60: "Bare / sparse vegetation", 70: "Permanent water",
    80: "Wetland (herbaceous)", 90: "Mangroves", 95: "Moss and lichen", 100: "NaN",
}


async def worldcover_grid(bbox: List[float], grid: int = 8) -> Dict[str, Any]:
    """Sample ESA WorldCover 2021 class codes on a grid over the bbox via WMS GetFeatureInfo."""
    import math
    from lib.geo import sample_grid

    pts = sample_grid(bbox, side=grid)
    span_lng = max(abs(bbox[2] - bbox[0]), 1e-6)
    span_lat = max(abs(bbox[3] - bbox[1]), 1e-6)
    w = h = 256
    codes: List[int] = []
    client = ext_http.get_client()

    async def one(lat: float, lng: float) -> int | None:
        params = {
            "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo",
            "LAYERS": "WORLDCOVER", "QUERY_LAYERS": "WORLDCOVER",
            "CRS": "EPSG:4326", "BBOX": f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}",
            "WIDTH": w, "HEIGHT": h, "INFO_FORMAT": "application/json",
            "I": int(round((lng - bbox[0]) / span_lng * (w - 1))),
            "J": int(round((bbox[3] - lat) / span_lat * (h - 1))),
        }
        r = await client.get(WORLDCOVER_WMS, params=params)
        if r.status_code != 200:
            raise RuntimeError(f"WMS HTTP {r.status_code}")
        val = r.json().get("features", [])
        if not val:
            return None
        return val[0].get("properties", {}).get("value")

    results = await __import__("asyncio").gather(*[one(lat, lng) for lat, lng in pts],
                                                 return_exceptions=True)
    ok = [r for r in results if isinstance(r, int) and r in WC_CLASSES and r != 100]
    if len(ok) < len(pts) * 0.4:
        raise RuntimeError("WorldCover WMS returned too few valid samples")
    counts: Dict[str, int] = {}
    for code in ok:
        counts[WC_CLASSES[code]] = counts.get(WC_CLASSES[code], 0) + 1
    total = len(ok)
    percentages = {k: round(100.0 * v / total, 1) for k, v in counts.items()}
    return {
        "percentages": percentages,
        "sample_points": total,
        "requested_points": len(pts),
        "classes": {str(k): v for k, v in WC_CLASSES.items() if k != 100},
        "source": "ESA WorldCover 2021 (Terrascope WMS)",
        "resolution": "approximately 10 m, sampled on a grid",
        "bbox_used": {"span_lng": round(span_lng, 6), "span_lat": round(span_lat, 6)},
        "_math_check": round(math.sqrt(max(span_lng * span_lat, 0)), 8),
    }
