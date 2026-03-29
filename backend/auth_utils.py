from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from config import settings

_password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@dataclass(frozen=True)
class AuthContext:
    username: str
    account_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    role: str | None
    is_superadmin: bool


def hash_password(password: str) -> str:
    return _password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_context.verify(password, password_hash)


def _encode_token(payload: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode(
        {**payload, "exp": expire},
        settings.jwt_secret,
        algorithm="HS256",
    )


def create_superadmin_token(username: str) -> str:
    return _encode_token(
        {
            "sub": username,
            "is_superadmin": True,
            "account_id": None,
            "workspace_id": None,
            "role": None,
        }
    )


def create_account_token(context: AuthContext) -> str:
    if context.account_id is None or context.workspace_id is None or context.role is None:
        raise ValueError("Account token requires account_id, workspace_id, and role")
    return _encode_token(
        {
            "sub": context.username,
            "is_superadmin": False,
            "account_id": str(context.account_id),
            "workspace_id": str(context.workspace_id),
            "role": context.role,
        }
    )


def decode_access_token(token: str) -> AuthContext:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    username = payload.get("sub")
    if not username:
        raise ValueError("Invalid token payload")

    account_id = payload.get("account_id")
    workspace_id = payload.get("workspace_id")

    return AuthContext(
        username=username,
        account_id=uuid.UUID(account_id) if account_id else None,
        workspace_id=uuid.UUID(workspace_id) if workspace_id else None,
        role=payload.get("role"),
        is_superadmin=bool(payload.get("is_superadmin", False)),
    )
