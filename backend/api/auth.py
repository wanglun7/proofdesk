from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from jose import jwt
from config import settings

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


def create_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode(
        {"sub": username, "exp": expire},
        settings.jwt_secret,
        algorithm="HS256",
    )


@router.post("/login")
async def login(body: LoginRequest):
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": create_token(body.username), "token_type": "bearer"}
