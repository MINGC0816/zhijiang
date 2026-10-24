from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from src.config import JWT_ALGORITHM, JWT_EXPIRE_HOURS, JWT_KB_ADMIN_EXPIRE_MINUTES, JWT_SECRET


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    *,
    user_id: str,
    username: str,
    role: str,
    token_type: str = "access",
    expires_delta: timedelta | None = None,
) -> str:
    if expires_delta is None:
        if token_type == "kb_admin":
            expires_delta = timedelta(minutes=JWT_KB_ADMIN_EXPIRE_MINUTES)
        else:
            expires_delta = timedelta(hours=JWT_EXPIRE_HOURS)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": token_type,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
