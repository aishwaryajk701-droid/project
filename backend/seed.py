"""AgriGaurd seed script — idempotent. Creates the admin account and sample fields.

Run: cd /app/backend && python seed.py
"""

import asyncio
from datetime import datetime, timezone

from lib.db import db, ensure_indexes
from lib.geo import bbox_from_polygon, polygon_area_ha
from lib.security import hash_password, new_id

ADMIN_EMAIL = "aishwaryajk701@gmail.com"
ADMIN_PASSWORD = "AgriGaurd@2026"
DEMO_USER_EMAIL = "farmer@agrigaurd.demo"
DEMO_USER_PASSWORD = "Farmer@2026"

# (name, state, district, village, coordinates [[lng, lat], ...])
SAMPLE_FIELDS = [
    ("Kosi River Basin Plot", "Bihar", "Katihar", "Barsoi",
     [[87.02, 25.42], [87.032, 25.42], [87.032, 25.432], [87.02, 25.432], [87.02, 25.42]]),
    ("Godavari Delta Paddy", "Andhra Pradesh", "West Godavari", "Bhimavaram",
     [[81.72, 16.53], [81.732, 16.53], [81.732, 16.542], [81.72, 16.542], [81.72, 16.53]]),
    ("Vidarbha Cotton Field", "Maharashtra", "Nagpur", "Katol",
     [[78.58, 21.28], [78.592, 21.28], [78.592, 21.292], [78.58, 21.292], [78.58, 21.28]]),
]


async def seed() -> None:
    await ensure_indexes()

    # Admin account (real owner email)
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    if not existing:
        await db.users.insert_one({
            "id": new_id(), "email": ADMIN_EMAIL, "name": "AgriGaurd Admin",
            "role": "ADMIN", "password_hash": hash_password(ADMIN_PASSWORD),
            "created_at": datetime.now(timezone.utc).isoformat()})
        print(f"admin created: {ADMIN_EMAIL}")
    else:
        await db.users.update_one({"email": ADMIN_EMAIL}, {"$set": {"role": "ADMIN"}})
        print(f"admin exists: {ADMIN_EMAIL}")

    # Demo farmer for exploring the app
    if not await db.users.find_one({"email": DEMO_USER_EMAIL}):
        await db.users.insert_one({
            "id": new_id(), "email": DEMO_USER_EMAIL, "name": "Demo Farmer",
            "role": "FARMER", "password_hash": hash_password(DEMO_USER_PASSWORD),
            "created_at": datetime.now(timezone.utc).isoformat()})
        print(f"demo farmer created: {DEMO_USER_EMAIL}")

    owner = await db.users.find_one({"email": DEMO_USER_EMAIL})
    admin = await db.users.find_one({"email": ADMIN_EMAIL})
    for user in (owner, admin):
        if not user:
            continue
        for name, state, district, village, coords in SAMPLE_FIELDS:
            key = {"user_id": user["id"], "name": name}
            if await db.fields.find_one(key):
                continue
            await db.fields.insert_one({
                "id": new_id(), "user_id": user["id"], "name": name,
                "state": state, "district": district, "village": village,
                "latitude": sum(p[1] for p in coords) / len(coords),
                "longitude": sum(p[0] for p in coords) / len(coords),
                "boundary": {"name": name, "coordinates": coords},
                "bbox": bbox_from_polygon(coords),
                "area_ha": round(polygon_area_ha(coords), 3),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_analysis": None, "flood_status": "UNKNOWN", "flood_pct": None,
                "flood_confidence": None, "land_suitability": None, "recommended_crop": None,
                "monitoring": {"enabled": False, "frequency": "weekly"}})
    print("sample fields ensured")


if __name__ == "__main__":
    asyncio.run(seed())
