"""Resilient async HTTP for external data sources.

- one shared httpx.AsyncClient (created lazily, closed at shutdown)
- Mongo-backed TTL cache keyed by sha256 of the normalized request
- timeout + retry with exponential backoff on transient errors
- `safe()` wrapper: any failure becomes {"status": "DATA UNAVAILABLE", ...} — never an exception
  that could destroy a whole analysis (partial-analysis rule).
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from bson import Binary

from lib.db import db

logger = logging.getLogger("agriguard.http")

TIMEOUT = httpx.Timeout(30.0, connect=8.0)
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
DEFAULT_TTL = 900  # 15 min
TTL_BY_SOURCE = {
    "weather": 1800,        # 30 min
    "weather_archive": 21600,  # 6 h
    "elevation": 7 * 24 * 3600,  # DEM does not change — 7 days
    "soil": 30 * 24 * 3600,      # SoilGrids static — 30 days
    "osm": 7 * 24 * 3600,        # OSM context — 7 days
    "geocode": 7 * 24 * 3600,
    "sh_catalog": 1800,
    "sh_process": 12 * 3600,
    "landcover": 30 * 24 * 3600,
}

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                    headers={"User-Agent": "AgriGaurd/1.0 (agricultural decision support)"})
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None


def cache_key(source: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return f"{source}:{hashlib.sha256(raw).hexdigest()}"


async def _read_cache(key: str) -> Optional[Any]:
    doc = await db.cache.find_one({"key": key})
    if not doc:
        return None
    exp = doc.get("expires_at")
    if exp is not None:
        # Mongo hands back naive UTC datetimes — normalise before comparing.
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return None
    val = doc.get("value")
    # Binary fields (images) come back as bson.Binary
    return bytes(val) if isinstance(val, Binary) else val


async def _write_cache(key: str, value: Any, ttl: int) -> None:
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    try:
        await db.cache.replace_one(
            {"key": key},
            {"key": key, "value": value, "expires_at": expires, "created_at": datetime.now(timezone.utc)},
            upsert=True)
    except Exception as exc:  # cache write failure must never fail a request
        logger.warning("cache write failed: %s", exc)


async def request(
    method: str,
    url: str,
    *,
    source: str = "misc",
    params: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    json_body: Any = None,
    content: Optional[bytes] = None,
    ttl: Optional[int] = None,
    retries: int = 3,
    cache_payload: Any = None,
) -> Any:
    """GET/POST with cache + retry. Returns parsed JSON, bytes, or text. Raises RuntimeError on final failure."""
    ckey = cache_key(source, cache_payload if cache_payload is not None
                     else {"m": method, "u": url, "p": params, "j": json_body, "c": content})
    ttl = ttl if ttl is not None else TTL_BY_SOURCE.get(source, DEFAULT_TTL)

    cached = await _read_cache(ckey)
    if cached is not None:
        return cached

    client = get_client()
    last_err = "request failed"
    for attempt in range(retries):
        try:
            r = await client.request(method, url, params=params, headers=headers,
                                     json=json_body, content=content)
            if r.status_code in RETRY_STATUS:
                last_err = f"upstream HTTP {r.status_code}"
                await asyncio.sleep(0.8 * (2 ** attempt))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"upstream HTTP {r.status_code}: {r.text[:200]}")
            ctype = r.headers.get("content-type", "")
            if "application/json" in ctype:
                value: Any = r.json()
            elif ctype.startswith("image/") or ctype in ("application/tiff", "image/tiff"):
                value = r.content
            else:
                value = r.text
            await _write_cache(ckey, value, ttl)
            return value
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_err = str(exc) or exc.__class__.__name__
            if attempt < retries - 1:
                await asyncio.sleep(0.8 * (2 ** attempt))
        except RuntimeError as exc:
            last_err = str(exc)
            if "HTTP 4" in last_err:  # client errors are pointless to retry
                break
    raise RuntimeError(last_err[:300])


def unavailable(name: str, error: str, detail: str = "") -> Dict[str, Any]:
    return {"status": "DATA UNAVAILABLE", "source": name, "data": None,
            "error": error[:240], "detail": detail, "fetched_at": None}


def available(name: str, data: Any, detail: str = "") -> Dict[str, Any]:
    return {"status": "OK", "source": name, "data": data, "error": None, "detail": detail,
            "fetched_at": datetime.now(timezone.utc).isoformat()}


async def safe(name: str, fn, detail: str = "") -> Dict[str, Any]:
    """Run `fn()`; never raise. Used for every external source so one outage → partial analysis."""
    t0 = time.time()
    try:
        data = await fn()
        return available(name, data, detail)
    except Exception as exc:
        logger.warning("source %s unavailable: %s", name, exc)
        return unavailable(name, str(exc), detail)
    finally:
        logger.info("source %s finished in %.2fs", name, time.time() - t0)
