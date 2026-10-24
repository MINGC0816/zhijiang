from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.security import decode_token
from src.auth.store import get_user_by_id

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    user_id: str
    username: str
    role: str
    status: str
    display_name: str
    email: str


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def get_client_ip(request: Request) -> str:
    return _client_ip(request)


def _row_to_auth_user(row: dict) -> AuthUser:
    return AuthUser(
        user_id=row["user_id"],
        username=row["username"],
        role=row["role"],
        status=row["status"],
        display_name=row.get("display_name") or row["username"],
        email=row.get("email") or "",
    )


def _user_from_token(token: str) -> AuthUser:
    try:
        payload = decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="无效或已过期的登录凭证") from exc
    if payload.get("type") not in {None, "access"}:
        raise HTTPException(status_code=401, detail="无效的登录凭证类型")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的登录凭证")
    row = get_user_by_id(user_id)
    if not row:
        raise HTTPException(status_code=401, detail="用户不存在")
    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="账号已冻结，请联系管理员")
    return _row_to_auth_user(row)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="请先登录")
    return _user_from_token(credentials.credentials)


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def _kb_admin_from_header(request: Request) -> AuthUser | None:
    token = request.headers.get("x-kb-admin-token")
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception:  # noqa: BLE001
        return None
    if payload.get("type") != "kb_admin" or payload.get("role") != "admin":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    row = get_user_by_id(user_id)
    if not row or row["role"] != "admin" or row["status"] != "active":
        return None
    return _row_to_auth_user(row)


def require_kb_admin(
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    if user.role == "admin":
        return user
    kb_admin = _kb_admin_from_header(request)
    if kb_admin:
        return kb_admin
    raise HTTPException(status_code=403, detail="需要管理员权限访问知识库管理")
