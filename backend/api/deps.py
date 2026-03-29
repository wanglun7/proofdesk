from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from auth_utils import AuthContext, decode_access_token

_bearer = HTTPBearer(auto_error=False)

async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(default=None),  # for EventSource (can't set headers)
) -> AuthContext:
    try:
        if creds:
            return decode_access_token(creds.credentials)
        if token:
            return decode_access_token(token)
    except (JWTError, ValueError):
        raise HTTPException(401, "Invalid or expired token")
    raise HTTPException(401, "Not authenticated")


async def require_superadmin(
    auth: AuthContext = Depends(get_current_user),
) -> AuthContext:
    if not auth.is_superadmin:
        raise HTTPException(403, "Superadmin access required")
    return auth


async def require_workspace_member(
    auth: AuthContext = Depends(get_current_user),
) -> AuthContext:
    if auth.workspace_id is None:
        raise HTTPException(403, "Workspace membership required")
    return auth
