from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from config import settings

_bearer = HTTPBearer(auto_error=False)


def _decode(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    username: str = payload.get("sub", "")
    if not username:
        raise HTTPException(401, "Invalid token")
    return username


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(default=None),  # for EventSource (can't set headers)
) -> str:
    try:
        if creds:
            return _decode(creds.credentials)
        if token:
            return _decode(token)
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    raise HTTPException(401, "Not authenticated")
