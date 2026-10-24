from datetime import timedelta
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException

from src.auth.deps import _user_from_token, require_admin, require_kb_admin, AuthUser
from src.auth.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("admin123")
    assert hashed != "admin123"
    assert verify_password("admin123", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("admin123", "not-a-hash")


def test_access_token_roundtrip():
    token = create_access_token(user_id="u1", username="alice", role="user")
    payload = decode_token(token)
    assert payload["sub"] == "u1"
    assert payload["username"] == "alice"
    assert payload["role"] == "user"
    assert payload["type"] == "access"


def test_expired_token_rejected():
    token = create_access_token(
        user_id="u1",
        username="alice",
        role="user",
        expires_delta=timedelta(seconds=-5),
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_user_from_token_rejects_kb_admin_type():
    token = create_access_token(
        user_id="u1",
        username="admin",
        role="admin",
        token_type="kb_admin",
    )
    with pytest.raises(HTTPException) as exc:
        _user_from_token(token)
    assert exc.value.status_code == 401


def test_user_from_token_frozen_account():
    token = create_access_token(user_id="u2", username="bob", role="user")
    frozen = {
        "user_id": "u2",
        "username": "bob",
        "role": "user",
        "status": "frozen",
        "display_name": "bob",
        "email": "",
    }
    with patch("src.auth.deps.get_user_by_id", return_value=frozen):
        with pytest.raises(HTTPException) as exc:
            _user_from_token(token)
        assert exc.value.status_code == 403


def test_user_from_token_missing_user():
    token = create_access_token(user_id="nope", username="ghost", role="user")
    with patch("src.auth.deps.get_user_by_id", return_value=None):
        with pytest.raises(HTTPException) as exc:
            _user_from_token(token)
        assert exc.value.status_code == 401


def test_require_admin_blocks_user_role():
    user = AuthUser(
        user_id="u1",
        username="alice",
        role="user",
        status="active",
        display_name="alice",
        email="",
    )
    with pytest.raises(HTTPException) as exc:
        require_admin(user)
    assert exc.value.status_code == 403


def test_require_kb_admin_allows_admin_role():
    admin = AuthUser(
        user_id="a1",
        username="admin",
        role="admin",
        status="active",
        display_name="admin",
        email="",
    )
    assert require_kb_admin(request=None, user=admin) is admin  # type: ignore[arg-type]
