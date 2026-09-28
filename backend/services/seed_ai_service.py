"""Seed AI — preserved from the original AgriGuard codebase (image genuineness via LLM vision)
plus the hardware capture API. Kept separate from satellite analysis."""

import base64
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from PIL import Image

from lib.db import db
from lib.security import new_id

logger = logging.getLogger("agriguard.seed")

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def analyze_seed_with_llm(image_b64: str, seed_type: Optional[str]) -> Dict[str, Any]:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"prediction": "unknown", "confidence": 0.0,
                "notes": "LLM key not configured", "raw": None}
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage

    session_id = f"seed-{uuid.uuid4()}"
    system = ("You are an agricultural seed quality inspector. Analyze the seed image and classify "
              "as 'genuine' (healthy, expected shape/color, no mold/damage/adulteration) or "
              "'suspicious' (damaged, moldy, discolored, broken, mixed with foreign matter). "
              "Return STRICT JSON only with keys: prediction ('genuine'|'suspicious'), "
              "confidence (0.0-1.0), reasoning (short string), defects (list of strings), "
              "seed_type_guess (string). No commentary, no markdown fences.")
    chat = LlmChat(api_key=api_key, session_id=session_id,
                   system_message=system).with_model("gemini", "gemini-2.0-flash")
    prompt = f"Seed type hint: {seed_type or 'unknown'}. Inspect this seed sample."
    msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)])
    try:
        resp = await chat.send_message(msg)
    except Exception as e:
        logger.error("LLM error: %s", e)
        return {"prediction": "unknown", "confidence": 0.0, "notes": f"LLM error: {e}", "raw": None}
    text = str(resp).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        j = json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        try:
            j = json.loads(text[start:end + 1]) if 0 <= start < end else {}
        except Exception:
            j = {}
    pred = str(j.get("prediction", "unknown")).lower()
    if pred not in ("genuine", "suspicious"):
        pred = "unknown"
    try:
        conf = float(j.get("confidence", 0.0) or 0.0)
    except Exception:
        conf = 0.0
    return {"prediction": pred, "confidence": max(0.0, min(1.0, conf)),
            "reasoning": j.get("reasoning", ""), "defects": j.get("defects", []),
            "seed_type_guess": j.get("seed_type_guess", seed_type or "unknown"),
            "raw": text[:2000]}


def preprocess_image_b64(image_b64: str) -> Dict[str, Any]:
    raw = base64.b64decode(image_b64)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image too large ({len(raw)} bytes); max {MAX_IMAGE_BYTES} bytes")
    im = Image.open(io.BytesIO(raw))
    if im.size[0] * im.size[1] > MAX_IMAGE_PIXELS:
        raise ValueError("Image dimensions exceed the allowed limit")
    im = im.convert("RGB")
    w, h = im.size
    scale = 1024 / max(w, h) if max(w, h) > 1024 else 1
    if scale < 1:
        im = im.resize((int(w * scale), int(h * scale)))
    arr = np_stats(im)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return {"processed_b64": base64.b64encode(buf.getvalue()).decode(), "stats": arr}


def np_stats(im: Image.Image) -> Dict[str, Any]:
    import numpy as np
    arr = np.asarray(im)
    return {"width": im.size[0], "height": im.size[1],
            "mean_rgb": [float(arr[..., i].mean()) for i in range(3)],
            "std_rgb": [float(arr[..., i].std()) for i in range(3)]}


async def save_seed_analysis(user: Dict[str, Any], *, image_b64: str, seed_type: Optional[str],
                             device_id: Optional[str], notes: Optional[str],
                             pre: Dict[str, Any], llm_res: Dict[str, Any]) -> Dict[str, Any]:
    rec = {"id": new_id(), "user_id": user["id"], "type": "seed",
           "seed_type": seed_type, "device_id": device_id, "notes": notes,
           "processed_image_b64": pre["processed_b64"], "stats": pre["stats"],
           "result": llm_res, "status": "ok" if llm_res.get("prediction") != "unknown" else "llm_unavailable",
           "created_at": now_iso()}
    await db.analyses.insert_one(rec.copy())
    rec.pop("_id", None)
    return rec


async def batch_summary(user: Dict[str, Any], *, seed_type: Optional[str], device_id: Optional[str],
                        items: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(items)
    genuine = sum(1 for it in items if it["result"].get("prediction") == "genuine")
    suspicious = sum(1 for it in items if it["result"].get("prediction") == "suspicious")
    unknown = total - genuine - suspicious
    confs = [it["result"].get("confidence", 0.0) for it in items if it["result"].get("prediction") == "genuine"]
    genuineness = round(100.0 * sum(confs) / total, 1) if total else 0.0
    verdict = "pass" if genuine == total and total > 0 else "fail" if suspicious > genuine else "review"
    rec = {"id": new_id(), "user_id": user["id"], "type": "seed_batch",
           "seed_type": seed_type, "device_id": device_id, "count": total,
           "summary": {"total": total, "genuine": genuine, "suspicious": suspicious, "unknown": unknown,
                       "avg_genuine_confidence": round(sum(confs) / len(confs), 3) if confs else 0.0,
                       "genuineness_score": genuineness, "verdict": verdict},
           "items": items, "status": "ok", "created_at": now_iso()}
    await db.analyses.insert_one(rec.copy())
    rec.pop("_id", None)
    return rec
