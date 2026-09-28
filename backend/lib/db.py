"""Shared Mongo handle — import `client`/`db` from here (server.py, routers, seed.py)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

load_dotenv(Path(__file__).parent.parent / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

logger = logging.getLogger(__name__)

# One entry per collection: every field a route filters, sorts, or dedupes on. Applied by ensure_indexes() at startup.
INDEXES: dict[str, list[IndexModel]] = {
    "status_checks": [IndexModel([("timestamp", DESCENDING)], name="timestamp_desc")],
    # --- AgriGaurd ---
    "users": [
        IndexModel([("email", ASCENDING)], name="email", unique=True),
        IndexModel([("created_at", ASCENDING)], name="created_asc"),
    ],
    "fields": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("user_id", ASCENDING), ("name", ASCENDING)], name="user_name"),
    ],
    "analyses": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("field_id", ASCENDING), ("created_at", DESCENDING)], name="field_created"),
        IndexModel([("type", ASCENDING), ("created_at", DESCENDING)], name="type_created"),
    ],
    "analysis_jobs": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("job_id", ASCENDING)], name="job_id", unique=True),
    ],
    "monitoring_configs": [
        IndexModel([("user_id", ASCENDING)], name="user_idx"),
        IndexModel([("field_id", ASCENDING)], name="field_idx"),
        IndexModel([("enabled", ASCENDING), ("next_run", ASCENDING)], name="due_scan"),
    ],
    "notifications": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("user_id", ASCENDING), ("read", ASCENDING)], name="user_unread"),
    ],
    "alert_prefs": [IndexModel([("user_id", ASCENDING)], name="user_idx", unique=True)],
    "audit_log": [IndexModel([("created_at", DESCENDING)], name="created_desc")],
    "devices": [IndexModel([("user_id", ASCENDING), ("device_id", ASCENDING)], name="user_device")],
    "rate_limits": [IndexModel([("key", ASCENDING)], name="key_idx")],
    "cache": [IndexModel([("expires_at", ASCENDING)], name="expires_ttl",
                         expireAfterSeconds=1)],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:  # one at a time so a bad spec skips only itself
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:  # never block boot on an index; the log line names what to fix
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)
