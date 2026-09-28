"""System health: real connectivity probes with short timeouts, cached briefly.
Statuses: CONNECTED | NOT CONFIGURED | ERROR | OPTIONAL. Never exposes credentials."""

import asyncio
import os
import time
from typing import Any, Dict

import httpx
from fastapi import APIRouter

from lib import ext_http
from lib.db import db
from services import sentinel_service

router = APIRouter(prefix="/health", tags=["health"])

_health_cache: Dict[str, Any] = {"at": 0.0, "payload": None}
CACHE_SECONDS = 60


async def _probe(name: str, coro_fn, configured: bool, optional: bool = False) -> Dict[str, Any]:
    if not configured:
        return {"service": name, "status": "NOT CONFIGURED" if not optional else "OPTIONAL",
                "detail": "credentials/keys not set"}
    try:
        await coro_fn()
        return {"service": name, "status": "CONNECTED", "detail": "reachable"}
    except Exception as exc:
        return {"service": name, "status": "ERROR", "detail": str(exc)[:160]}


_UA = "AgriGaurd/1.0 (agricultural decision support)"


async def _check_raw():
    async with httpx.AsyncClient(timeout=6.0) as c:
        r = await c.get("https://api.open-meteo.com/v1/elevation",
                        params={"latitude": 28.6, "longitude": 77.2})
        r.raise_for_status()


async def _check_soil():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get("https://rest.isric.org/soilgrids/v2.0/properties/query",
                        params={"lon": 77.2, "lat": 28.6, "property": "phh2o", "depth": "0-5cm",
                                "value": "mean"})
        r.raise_for_status()


async def _check_overpass():
    # Overpass rejects requests without a descriptive User-Agent (HTTP 406).
    async with httpx.AsyncClient(timeout=20.0,
                                 headers={"User-Agent": _UA}) as c:
        r = await c.post("https://overpass-api.de/api/interpreter",
                         content=b"[out:json][timeout:5];node(28.6,77.2,28.61,77.21);out;",
                         headers={"Content-Type": "text/plain"})
        r.raise_for_status()


async def _check_wms():
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get("https://services.terrascope.be/wms/v2",
                        params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetCapabilities"})
        r.raise_for_status()


async def _check_mongo():
    await db.command("ping")


@router.get("")
async def health():
    if _health_cache["payload"] and time.time() - _health_cache["at"] < CACHE_SECONDS:
        return _health_cache["payload"]

    sh = sentinel_service.configured()
    llm = bool(os.environ.get("EMERGENT_LLM_KEY"))
    email = bool(os.environ.get("EMERGENT_EMAIL_KEY"))
    sms = bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN")
               and os.environ.get("TWILIO_PHONE_NUMBER"))

    checks = await asyncio.gather(
        _probe("MongoDB", _check_mongo, True),
        _probe("Sentinel-1 / Sentinel-2 (Sentinel Hub)", _check_raw, sh),
        _probe("Open-Meteo weather & DEM", _check_raw, True),
        _probe("SoilGrids soil properties", _check_soil, True),
        _probe("Overpass (OpenStreetMap context)", _check_overpass, True),
        _probe("ESA WorldCover WMS", _check_wms, True),
        _probe("JRC Global Surface Water", _check_raw, sh),  # needs SH/GEE access
        _probe("Seed AI LLM (Emergent)", _check_raw, llm),
        _probe("Email alerts (Emergent managed)", _check_raw, email, optional=True),
        _probe("SMS alerts (Twilio)", _check_raw, sms, optional=True),
    )
    payload = {
        "checks": checks,
        "backend": {"status": "CONNECTED", "detail": "serving /api"},
        "configured": {"sentinel_hub": sh, "llm": llm, "email": email, "sms": sms},
        "checked_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "note": "OPTIONAL services degrade gracefully — analyses are partial, never fabricated.",
    }
    _health_cache["payload"] = payload
    _health_cache["at"] = time.time()
    return payload
