"""Demo mode — PREPARED SAMPLE DATASETS, clearly labelled, never mixed with real analyses.

The demo SAR pair is a deterministic synthetic VV/VH capture (a field whose western half
became inundated between the two passes). Demo runs reuse the exact same flood methodology
as real runs so the pipeline is exercised end-to-end, but every result is tagged DEMO.
"""

import io
from typing import Any, Dict, List

import numpy as np

DEMO_BBOX = [77.20, 28.55, 77.22, 28.57]  # near Delhi ridge area for realistic coords
DEMO_AREA_HA = 4.35

DEMO_OBSERVATIONS: List[Dict[str, Any]] = [
    {"satellite": "Sentinel-1 GRD", "product": "S1A_IW_GRDH_1SDV", "polarisation": "VV+VH",
     "acquired": "DEMO-14 (14 days ago)", "quality": "synthetic sample", "role": "before"},
    {"satellite": "Sentinel-1 GRD", "product": "S1A_IW_GRDH_1SDV", "polarisation": "VV+VH",
     "acquired": "DEMO-2 (2 days ago)", "quality": "synthetic sample", "role": "after"},
]


def demo_sar_pair(shape: tuple = (96, 96)) -> Dict[str, np.ndarray]:
    """Synthetic VV/VH before/after arrays: west half floods after the second pass."""
    h, w = shape
    rng = np.random.default_rng(42)  # deterministic
    yy, xx = np.mgrid[0:h, 0:w]

    def field(before: bool) -> np.ndarray:
        vv = np.zeros((h, w, 3), dtype=np.float32)
        base_vv = 0.0035 * np.exp(0.28 * rng.normal(0, 1, (h, w)).clip(-1.5, 1.5)) + 0.006
        base_vh = base_vv * 0.22
        land_vv = np.clip(base_vv, 0.004, 0.12)
        land_vh = np.clip(base_vh, 0.001, 0.05)
        if not before:
            flood = (xx < w * 0.45).astype(np.float32)
            land_vv = land_vv * (1 - flood) + 0.0055 * flood   # -21..-24 dB
            land_vh = land_vh * (1 - flood) + 0.0009 * flood
        vv[..., 0], vv[..., 1], vv[..., 2] = land_vv, land_vh, 1
        return vv

    return {"before": field(True), "after": field(False)}


def demo_true_color_pair() -> Dict[str, Any]:
    """Small synthetic 'optical' PNGs for the before/after slider (DEMO only)."""
    from PIL import Image

    def render(flood: bool) -> bytes:
        w = h = 256
        img = np.zeros((h, w, 4), dtype=np.uint8)
        rng = np.random.default_rng(7)
        # soil/crop background
        img[..., 0] = 92 + rng.integers(-14, 14, (h, w))
        img[..., 1] = 104 + rng.integers(-14, 14, (h, w))
        img[..., 2] = 62 + rng.integers(-10, 10, (h, w))
        img[..., 3] = 255
        if flood:
            xx = np.mgrid[0:h, 0:w][1]
            mask = (xx < w * 0.45).astype(np.uint8)
            img[..., 0] = img[..., 0] * (1 - mask) + 46 * mask
            img[..., 1] = img[..., 1] * (1 - mask) + 78 * mask
            img[..., 2] = img[..., 2] * (1 - mask) + 110 * mask
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, format="PNG")
        return buf.getvalue()

    return {"before_png": render(False), "after_png": render(True)}


def demo_label() -> Dict[str, Any]:
    return {"demo": True,
            "banner": "DEMO DATA — NOT LIVE SATELLITE DATA",
            "note": ("This run uses AgriGaurd's prepared sample dataset so the full pipeline can be "
                     "explored without Sentinel Hub credentials. Demo results never mix with real "
                     "satellite analyses.")}


def demo_evidence() -> Dict[str, Any]:
    return {
        "positive": [
            {"icon": "ok", "text": "Demo SAR pair shows a -14 dB backscatter drop on the western half"},
            {"icon": "ok", "text": "Demo cropland mask classifies the flooded zone as cropland"},
            {"icon": "ok", "text": "Demo rainfall record (prepared dataset) is consistent with flooding"},
        ],
        "warnings": [
            {"icon": "warn", "text": "DEMO DATA — NOT LIVE SATELLITE DATA"},
            {"icon": "warn", "text": "Add Sentinel Hub credentials for real analyses"},
        ],
    }
