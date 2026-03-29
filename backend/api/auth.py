from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import AuthContext, create_account_token, create_superadmin_token, hash_password, verify_password
from config import settings
from database import get_db
from models import Account, Membership, Workspace
from api.deps import require_superadmin

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class BootstrapWorkspaceRequest(BaseModel):
    workspace_name: str
    owner_username: str
    owner_password: str


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    if body.username == settings.admin_username and body.password == settings.admin_password:
        return {
            "access_token": create_superadmin_token(body.username),
            "token_type": "bearer",
            "is_superadmin": True,
        }

    result = await db.execute(select(Account).where(Account.username == body.username))
    account = result.scalar_one_or_none()
    if not account or not account.is_active or not verify_password(body.password, account.password_hash):
        raise HTTPException(401, "Invalid username or password")

    membership_result = await db.execute(
        select(Membership)
        .where(Membership.account_id == account.id)
        .order_by(Membership.created_at.asc())
    )
    membership = membership_result.scalar_one_or_none()
    if not membership:
        raise HTTPException(403, "Account is not assigned to a workspace")

    auth = AuthContext(
        username=account.username,
        account_id=account.id,
        workspace_id=membership.workspace_id,
        role=membership.role,
        is_superadmin=False,
    )
    return {
        "access_token": create_account_token(auth),
        "token_type": "bearer",
        "is_superadmin": False,
        "workspace_id": str(membership.workspace_id),
        "role": membership.role,
    }


@router.post("/bootstrap/workspace")
async def bootstrap_workspace(
    body: BootstrapWorkspaceRequest,
    db: AsyncSession = Depends(get_db),
    _: AuthContext = Depends(require_superadmin),
):
    existing = await db.execute(select(Account).where(Account.username == body.owner_username))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Username already exists")

    workspace = Workspace(name=body.workspace_name)
    account = Account(
        username=body.owner_username,
        password_hash=hash_password(body.owner_password),
    )
    db.add(workspace)
    db.add(account)
    await db.flush()

    membership = Membership(
        workspace_id=workspace.id,
        account_id=account.id,
        role="owner",
    )
    db.add(membership)
    await db.commit()
    await db.refresh(workspace)
    await db.refresh(account)

    return {
        "workspace_id": str(workspace.id),
        "workspace_name": workspace.name,
        "owner_account_id": str(account.id),
        "owner_username": account.username,
        "role": membership.role,
    }
