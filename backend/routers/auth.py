"""Authentication: register / login / logout / me. JWT rides an httpOnly cookie
(same-origin via the /api proxy) and is also returned for API clients using Bearer."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Response

from lib.db import db
from lib.security import (JWT_TTL_SECONDS, current_user, hash_password, make_token, new_id,
                          verify_password)
from models.agrigaurd import LoginIn, RegisterIn, TokenOut, UserOut
from services.notification_service import audit

logger = logging.getLogger("agriguard.auth")

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "agrigaurd_token"


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                        max_age=JWT_TTL_SECONDS, path="/")


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn, response: Response):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    uid = new_id()
    doc = {"id": uid, "email": body.email.lower(), "name": body.name, "role": "FARMER",
           "password_hash": hash_password(body.password),
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.users.insert_one(doc)
    token = make_token(uid, body.email.lower())
    _set_cookie(response, token)
    await audit(uid, "register", {"email": body.email.lower()})
    return TokenOut(access_token=token,
                    user=UserOut(id=uid, email=body.email.lower(), name=body.name, role="FARMER"))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, response: Response):
    u = await db.users.find_one({"email": body.email.lower()})
    if not u or not verify_password(body.password, u.get("password_hash", "")):
        raise HTTPException(401, "Invalid credentials")
    token = make_token(u["id"], u["email"])
    _set_cookie(response, token)
    await audit(u["id"], "login", {})
    return TokenOut(access_token=token,
                    user=UserOut(id=u["id"], email=u["email"], name=u.get("name", ""),
                                 role=u.get("role", "FARMER")))


@router.post("/logout")
async def logout(response: Response, user: Dict[str, Any] = Depends(current_user)):
    response.delete_cookie(COOKIE, path="/")
    await audit(user["id"], "logout", {})
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: Dict[str, Any] = Depends(current_user)):
    return UserOut(id=user["id"], email=user["email"], name=user.get("name", ""),
                   role=user.get("role", "FARMER"))
