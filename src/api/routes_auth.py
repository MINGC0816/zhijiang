from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.auth.deps import AuthUser, get_client_ip, get_current_user, require_admin
from src.auth.security import create_access_token, verify_password
from src.auth.store import (
    create_user,
    delete_user,
    get_user_by_username,
    list_audit_logs,
    list_users,
    reset_user_password,
    update_user,
    write_audit_log,
)
from src.logging_config import get_logger

log = get_logger("qizhi.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)
    display_name: str = Field(default="", max_length=64)
    email: str = Field(default="", max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class KbAdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class KbAdminTokenResponse(BaseModel):
    kb_admin_token: str
    token_type: str = "kb_admin"
    expires_in_minutes: int


def _issue_token(user: dict) -> AuthTokenResponse:
    token = create_access_token(
        user_id=user["user_id"],
        username=user["username"],
        role=user["role"],
    )
    return AuthTokenResponse(access_token=token, user=user)


@router.post("/register", response_model=AuthTokenResponse)
def auth_register(body: RegisterRequest, request: Request):
    username = body.username.strip()
    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    try:
        user = create_user(
            username=username,
            password=body.password,
            display_name=body.display_name,
            email=body.email,
            role="user",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ip = get_client_ip(request)
    write_audit_log(
        action="register",
        user_id=user["user_id"],
        username=user["username"],
        detail="用户注册",
        ip_address=ip,
    )
    log.info("user registered username=%s", username)
    return _issue_token(user)


@router.post("/login", response_model=AuthTokenResponse)
def auth_login(body: LoginRequest, request: Request):
    row = get_user_by_username(body.username)
    if not row or not verify_password(body.password, row["password_hash"]):
        write_audit_log(
            action="login_failed",
            username=body.username.strip(),
            detail="登录失败：用户名或密码错误",
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="账号已冻结，请联系管理员")
    user = {k: v for k, v in row.items() if k != "password_hash"}
    write_audit_log(
        action="login",
        user_id=user["user_id"],
        username=user["username"],
        detail="用户登录",
        ip_address=get_client_ip(request),
    )
    log.info("user login username=%s role=%s", user["username"], user["role"])
    return _issue_token(user)


@router.post("/logout")
def auth_logout(
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    write_audit_log(
        action="logout",
        user_id=user.user_id,
        username=user.username,
        detail="用户登出",
        ip_address=get_client_ip(request),
    )
    return {"ok": True}


@router.get("/me")
def auth_me(user: AuthUser = Depends(get_current_user)):
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "display_name": user.display_name,
        "email": user.email,
    }


@router.post("/kb-admin-login", response_model=KbAdminTokenResponse)
def auth_kb_admin_login(body: KbAdminLoginRequest, request: Request):
    """普通用户进入知识库管理前，需用管理员账号二次验证。"""
    row = get_user_by_username(body.username)
    if not row or not verify_password(body.password, row["password_hash"]):
        write_audit_log(
            action="kb_admin_login_failed",
            username=body.username.strip(),
            detail="知识库管理员验证失败",
            ip_address=get_client_ip(request),
        )
        raise HTTPException(status_code=401, detail="管理员用户名或密码错误")
    if row["role"] != "admin":
        raise HTTPException(status_code=403, detail="该账号不是管理员")
    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="管理员账号已冻结")
    token = create_access_token(
        user_id=row["user_id"],
        username=row["username"],
        role="admin",
        token_type="kb_admin",
    )
    write_audit_log(
        action="kb_admin_login",
        user_id=row["user_id"],
        username=row["username"],
        detail="知识库管理授权",
        ip_address=get_client_ip(request),
    )
    from src.config import JWT_KB_ADMIN_EXPIRE_MINUTES

    return KbAdminTokenResponse(
        kb_admin_token=token,
        expires_in_minutes=JWT_KB_ADMIN_EXPIRE_MINUTES,
    )


admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin-users"])


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    status: str | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=64)


@admin_router.get("/users")
def admin_list_users(_admin: AuthUser = Depends(require_admin)):
    return {"users": list_users(role="user")}


@admin_router.patch("/users/{user_id}")
def admin_update_user(
    user_id: str,
    body: UpdateUserRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
):
    try:
        user = update_user(
            user_id,
            display_name=body.display_name,
            email=body.email,
            status=body.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    detail = f"管理员 {admin.username} 更新用户 {user['username']}"
    if body.status:
        detail += f"，状态={body.status}"
    write_audit_log(
        action="user_update",
        user_id=admin.user_id,
        username=admin.username,
        detail=detail,
        ip_address=get_client_ip(request),
    )
    return user


@admin_router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    request: Request,
    admin: AuthUser = Depends(require_admin),
):
    from src.auth.store import get_user_by_id

    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        ok = reset_user_password(user_id, body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    write_audit_log(
        action="password_reset",
        user_id=admin.user_id,
        username=admin.username,
        detail=f"管理员 {admin.username} 重置用户 {target['username']} 的密码",
        ip_address=get_client_ip(request),
    )
    return {"ok": True}


@admin_router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: str,
    request: Request,
    admin: AuthUser = Depends(require_admin),
):
    from src.auth.store import get_user_by_id

    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    try:
        ok = delete_user(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    write_audit_log(
        action="user_delete",
        user_id=admin.user_id,
        username=admin.username,
        detail=f"管理员 {admin.username} 删除用户 {target['username']}",
        ip_address=get_client_ip(request),
    )
    return {"ok": True}


@admin_router.get("/audit-logs")
def admin_audit_logs(
    action: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _admin: AuthUser = Depends(require_admin),
):
    cap = max(1, min(limit, 500))
    off = max(0, offset)
    return {
        "logs": list_audit_logs(
            action=action or None,
            user_id=user_id or None,
            limit=cap,
            offset=off,
        )
    }
