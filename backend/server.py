"""AgriGaurd — AI-Powered Satellite Agricultural Flood Monitoring, Land Suitability and
Crop Intelligence Platform.

FastAPI entry point. All routes live on api_router under /api; app.include_router stays last.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from lib.db import client, db, ensure_indexes
from lib.ext_http import close_client
from routers import cron, insights
from routers import (admin, alerts, analysis, auth, crops, fields, health, reports, satellite,
                     seed_ai)
from services.monitoring_service import scheduler_loop

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("agriguard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index_task = asyncio.create_task(ensure_indexes())
    monitor_task = asyncio.create_task(scheduler_loop())
    yield
    monitor_task.cancel()
    await close_client()
    client.close()


app = FastAPI(
    title="AgriGaurd API",
    description=("AI-Powered Satellite Agricultural Flood Monitoring, Land Suitability and Crop "
                 "Intelligence Platform. Sentinel-1 SAR + Sentinel-2 optical (when Sentinel Hub "
                 "credentials are configured) combined with Copernicus DEM, SoilGrids, Open-Meteo "
                 "and OpenStreetMap context. All endpoints require JWT auth except health & docs."),
    version="2.0.0",
)

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(fields.router)
api_router.include_router(analysis.router)
api_router.include_router(satellite.router)
api_router.include_router(alerts.router)
api_router.include_router(reports.router)
api_router.include_router(crops.router)
api_router.include_router(admin.router)
api_router.include_router(health.router)
api_router.include_router(seed_ai.router)
api_router.include_router(insights.router)
api_router.include_router(cron.router)


@api_router.get("/")
async def root():
    return {"message": "AgriGaurd API", "status": "ok", "docs": "/docs"}


# Include the router in the main app — always the LAST router statement
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
