"""Optional Twilio SMS alerts. Absent credentials degrade to in-app + email only."""

import logging
import os
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agriguard.sms")

SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
FROM = os.environ.get("TWILIO_PHONE_NUMBER", "")


def sms_configured() -> bool:
    return bool(SID and TOKEN and FROM)


def flood_alert_sms(*, field_name: str, severity: str, flood_pct: Any, affected_ha: Any) -> str:
    return (f"AgriGaurd {severity.upper()} flood alert — {field_name}: "
            f"{flood_pct}% agricultural flood, {affected_ha} ha affected. "
            f"Remote-sensing estimate; field verification recommended.")


async def send_sms(*, to: str, body: str) -> Optional[str]:
    if not sms_configured() or not to:
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json",
                auth=(SID, TOKEN),
                data={"From": FROM, "To": to, "Body": body[:600]})
        r.raise_for_status()
        return r.json().get("sid")
    except Exception as exc:
        logger.error("sms send failed: %s", exc)
        return None
