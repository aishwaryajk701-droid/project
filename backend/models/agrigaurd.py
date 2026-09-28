"""Pydantic v2 models shared across routers — every model here has a hand-written TS mirror
in frontend/src/lib/types.ts. Keep the pair in sync in the same edit."""

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must be at least 8 characters and include a letter and a number")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str = "FARMER"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BoundaryIn(BaseModel):
    name: Optional[str] = "Field"
    coordinates: List[List[float]]
    center: Optional[List[float]] = None


class FieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: Optional[str] = None
    district: Optional[str] = None
    village: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinates: List[List[float]]


class FieldUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    state: Optional[str] = None
    district: Optional[str] = None
    village: Optional[str] = None


class AnalyzeIn(BaseModel):
    coordinates: List[List[float]]
    field_id: Optional[str] = None
    save_as_field: bool = False
    field_name: Optional[str] = None
    demo: bool = False


class MonitoringIn(BaseModel):
    frequency: str  # daily | every_3_days | weekly
    enabled: bool = True


class AlertPrefsIn(BaseModel):
    email_enabled: bool = False
    alert_email: Optional[EmailStr] = None
    sms_enabled: bool = False
    alert_phone: Optional[str] = None
    min_severity: Optional[str] = "moderate"

    @field_validator("alert_phone")
    @classmethod
    def valid_phone(cls, v):
        if v is None or str(v).strip() == "":
            return v
        v = str(v).strip()
        if not E164_RE.match(v):
            raise ValueError("Phone must be in E.164 format, e.g. +14155552671")
        return v


class SeedAnalyzeIn(BaseModel):
    image_base64: str
    seed_type: Optional[str] = None
    device_id: Optional[str] = None
    notes: Optional[str] = None


class SeedBatchIn(BaseModel):
    images_base64: List[str]
    seed_type: Optional[str] = None
    device_id: Optional[str] = None


class HardwareRegisterIn(BaseModel):
    device_id: str
    name: Optional[str] = "AgriGaurd Seed Camera"
    firmware: Optional[str] = None


class HardwareImageIn(BaseModel):
    device_id: str
    image_base64: str
    seed_type: Optional[str] = None


class DiscoverIn(BaseModel):
    coordinates: List[List[float]]


class RecommendIn(BaseModel):
    coordinates: List[List[float]]
    state: Optional[str] = None
