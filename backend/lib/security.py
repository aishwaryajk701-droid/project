"""Auth primitives: bcrypt hashing, JWT (HS256, 7-day expiry), role dependencies.

Sessions ride httpOnly cookies set by the auth router; this module owns encode/verify.
.env is self-loaded so standalone scripts (seed.py) inherit config too.
"""

import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict

import bcrypt
import jwt as pyjwt
from dotenv import load_dotenv
from fastapi import Cookie, Depends, Header, HTTPException

load_dotenv(Path(__file__).parent.parent / ".env")

JWT_SECRET = os.environ.get("JWT_SECRET") or ""
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET missing from backend/.env")
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 7 * 24 * 3600

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
ROLES = ("FARMER", "ADMIN", "RESEARCHER")


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def make_token(user_id: str, email: str) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "email": email, "iat": now, "exp": now + JWT_TTL_SECONDS}
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired — sign in again")
    except Exception as exc:
        raise HTTPException(401, f"Invalid token: {exc}")


def token_from_cookie_or_header(authorization: str | None, cookie_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1]
    if cookie_token:
        return cookie_token
    raise HTTPException(401, "Not authenticated")


async def current_user(
    authorization: str | None = Header(None),
    agrigaurd_token: str | None = Cookie(None),
) -> Dict[str, Any]:
    """FastAPI dependency: JWT from the httpOnly cookie or an Authorization: Bearer header."""
    token = token_from_cookie_or_header(authorization, agrigaurd_token)
    data = decode_token(token)
    from lib.db import db  # local import: avoid cycle at module import time

    user = await db.users.find_one({"id": data["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


def require_role(*roles: str):
    async def checker(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        if user.get("role", "FARMER") not in roles:
            raise HTTPException(403, "Insufficient role")
        return user

    return checker


def new_id() -> str:
    return str(uuid.uuid4())
