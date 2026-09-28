"""PDF report generation endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from lib.db import db
from lib.security import current_user
from services.notification_service import audit
from services.report_service import build_report

router = APIRouter(prefix="/reports", tags=["reports"])


async def _analysis_and_field(analysis_id: str, user: Dict[str, Any]):
    doc = await db.analyses.find_one({"id": analysis_id, "user_id": user["id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Analysis not found")
    field = None
    if doc.get("field_id"):
        field = await db.fields.find_one({"id": doc["field_id"], "user_id": user["id"]}, {"_id": 0})
    return doc, field


@router.get("/analyses/{analysis_id}/report.pdf")
async def analysis_report(analysis_id: str, user: Dict[str, Any] = Depends(current_user)):
    doc, field = await _analysis_and_field(analysis_id, user)
    pdf = build_report(doc, field, user.get("email", ""))
    await audit(user["id"], "report_generated", {"analysis_id": analysis_id})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=agrigaurd-report-{analysis_id[:8]}.pdf"})


@router.get("/fields/{field_id}/report.pdf")
async def field_report(field_id: str, user: Dict[str, Any] = Depends(current_user)):
    field = await db.fields.find_one({"id": field_id, "user_id": user["id"]}, {"_id": 0})
    if not field:
        raise HTTPException(404, "Field not found")
    doc = await db.analyses.find_one({"field_id": field_id, "user_id": user["id"], "type": "satellite"},
                                     {"_id": 0}, sort=[("created_at", -1)])
    if not doc:
        raise HTTPException(404, "No analysis available for this field yet — run an analysis first")
    pdf = build_report(doc, field, user.get("email", ""))
    await audit(user["id"], "report_generated", {"field_id": field_id})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=agrigaurd-field-{field_id[:8]}.pdf"})
