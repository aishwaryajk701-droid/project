"""Seed AI (image genuineness) + hardware device API — preserved from the original codebase."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from lib.db import db
from lib.security import current_user, new_id
from models.agrigaurd import (HardwareImageIn, HardwareRegisterIn, SeedAnalyzeIn, SeedBatchIn)
from services import seed_ai_service
from services.notification_service import audit

router = APIRouter(tags=["seed-ai"])


@router.post("/seed/analyze")
async def seed_analyze(body: SeedAnalyzeIn, user: Dict[str, Any] = Depends(current_user)):
    try:
        pre = seed_ai_service.preprocess_image_b64(body.image_base64)
    except Exception as e:
        raise HTTPException(400, f"Invalid image: {e}")
    llm_res = await seed_ai_service.analyze_seed_with_llm(pre["processed_b64"], body.seed_type)
    rec = await seed_ai_service.save_seed_analysis(
        user, image_b64=body.image_base64, seed_type=body.seed_type, device_id=body.device_id,
        notes=body.notes, pre=pre, llm_res=llm_res)
    await audit(user["id"], "seed_analyzed", {"prediction": llm_res.get("prediction")})
    return rec


@router.post("/seed/batch-analyze")
async def seed_batch_analyze(body: SeedBatchIn, user: Dict[str, Any] = Depends(current_user)):
    if not body.images_base64:
        raise HTTPException(400, "Provide at least one seed image")
    if len(body.images_base64) > 24:
        raise HTTPException(400, "Maximum 24 seeds per batch")

    async def one(idx: int, img_b64: str) -> Dict[str, Any]:
        try:
            pre = seed_ai_service.preprocess_image_b64(img_b64)
        except Exception as e:
            return {"index": idx, "status": "error", "error": f"Invalid image: {e}",
                    "result": {"prediction": "unknown", "confidence": 0.0}}
        res = await seed_ai_service.analyze_seed_with_llm(pre["processed_b64"], body.seed_type)
        return {"index": idx, "status": "ok", "thumb_b64": pre["processed_b64"],
                "stats": pre["stats"], "result": res}

    items = await asyncio.gather(*[one(i, b) for i, b in enumerate(body.images_base64)])
    items.sort(key=lambda x: x["index"])
    rec = await seed_ai_service.batch_summary(user, seed_type=body.seed_type,
                                              device_id=body.device_id, items=items)
    await audit(user["id"], "seed_batch_analyzed", {"count": len(items)})
    return rec


# ------------------------- Hardware -------------------------

@router.post("/hardware/register")
async def hw_register(body: HardwareRegisterIn, user: Dict[str, Any] = Depends(current_user)):
    doc = {"id": new_id(), "user_id": user["id"], "device_id": body.device_id,
           "name": body.name, "firmware": body.firmware, "status": "online",
           "last_seen": datetime.now(timezone.utc).isoformat(),
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.devices.update_one({"user_id": user["id"], "device_id": body.device_id},
                                {"$set": doc}, upsert=True)
    doc.pop("_id", None)
    return doc


@router.get("/hardware/devices")
async def hw_list(user: Dict[str, Any] = Depends(current_user)):
    docs = await db.devices.find({"user_id": user["id"]}, {"_id": 0}).to_list(100)
    now = datetime.now(timezone.utc)
    for d in docs:
        try:
            seen = datetime.fromisoformat(d["last_seen"])
            if (now - seen).total_seconds() > 120:
                d["status"] = "offline"
        except Exception:
            d["status"] = "unknown"
    return docs


@router.post("/hardware/ping/{device_id}")
async def hw_ping(device_id: str, user: Dict[str, Any] = Depends(current_user)):
    r = await db.devices.update_one(
        {"user_id": user["id"], "device_id": device_id},
        {"$set": {"last_seen": datetime.now(timezone.utc).isoformat(), "status": "online"}})
    if r.matched_count == 0:
        raise HTTPException(404, "Device not registered")
    return {"ok": True, "device_id": device_id}


@router.post("/hardware/capture")
async def hw_capture(body: HardwareImageIn, user: Dict[str, Any] = Depends(current_user)):
    dev = await db.devices.find_one({"user_id": user["id"], "device_id": body.device_id})
    if not dev:
        raise HTTPException(404, "Device not registered. Register first at /api/hardware/register")
    await db.devices.update_one({"_id": dev["_id"]},
                                {"$set": {"last_seen": datetime.now(timezone.utc).isoformat(),
                                          "status": "online"}})
    seed_body = SeedAnalyzeIn(image_base64=body.image_base64, seed_type=body.seed_type,
                              device_id=body.device_id, notes="Captured from hardware")
    return await seed_analyze(seed_body, user)
