"""NISAR support — integration interface only.

NISAR L-band SAR products are distributed through NASA Earthdata / ASF. Until
Earthdata credentials are configured (and NISAR L2 products cover the AOI and date),
this service reports DATA UNAVAILABLE for the AOI. It never fabricates SAR evidence
and never fails the surrounding analysis.
"""

import os
from typing import Any, Dict, List


def configured() -> bool:
    return bool(os.environ.get("NASA_API_KEY") or os.environ.get("EARTHDATA_TOKEN"))


async def search_scenes(bbox: List[float], days: int = 60) -> Dict[str, Any]:
    if not configured():
        return {
            "available": False,
            "status": "NOT CONFIGURED",
            "scenes": [],
            "role": "Additional L-band SAR flood evidence (optional)",
            "source": "NISAR via NASA Earthdata / ASF",
            "message": ("NISAR data unavailable for this AOI/date — NASA Earthdata credentials "
                        "are not configured on this server (set NASA_API_KEY or EARTHDATA_TOKEN). "
                        "No NISAR evidence is used and nothing is estimated in its place."),
        }
    # Credentials present but no public NISAR L2 granule coverage is assumed for this AOI.
    return {
        "available": False,
        "status": "NO COVERAGE",
        "scenes": [],
        "role": "Additional L-band SAR flood evidence (optional)",
        "source": "NISAR via NASA Earthdata / ASF",
        "message": ("NISAR data unavailable for this AOI/date. The analysis continues on "
                    "Sentinel-1 SAR evidence; no NISAR values are estimated."),
    }
