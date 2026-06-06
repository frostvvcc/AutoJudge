from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware.rate_limit import limiter
from app.auth.blacklist import blacklist_token, is_blacklisted
from app.auth.deps import get_current_user
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.password import hash_password, verify_password
from app.db.engine import get_session
from app.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ---------- Request / Response schemas ----------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: str = Field(max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_一-鿿]+$", v):
            raise ValueError("用户名只能包含字母、数字、下划线和中文")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("邮箱格式无效")
        return v.strip().lower()


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, description="用户名或邮箱")
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    uid: str
    username: str
    email: str
    avatar_url: str | None
    created_at: datetime
    debate_count: int


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class UpdateProfileRequest(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=50)
    avatar_url: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ---------- Helpers ----------

def _user_info(user: User) -> UserInfo:
    return UserInfo(
        uid=user.uid,
        username=user.username,
        email=user.email,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        debate_count=user.debate_count,
    )


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.uid),
        refresh_token=create_refresh_token(user.id, user.uid),
        user=_user_info(user),
    )


# ---------- Endpoints ----------

@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_session)):
    existing = await db.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户名或邮箱已被注册")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("user_registered uid=%s username=%s", user.uid, user.username)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(User).where(
            (User.username == body.login) | (User.email == body.login)
        )
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名/邮箱或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已禁用")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("user_login uid=%s", user.uid)
    return _token_response(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_session)):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")

    jti = payload.get("jti")
    if jti and await is_blacklisted(jti):
        raise HTTPException(status_code=401, detail="刷新令牌已注销")

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在")

    if jti and payload.get("exp"):
        await blacklist_token(jti, payload["exp"])

    return _token_response(user)


@router.post("/logout")
async def logout(request: Request):
    """Revoke the current access token by adding its jti to the blacklist."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少认证令牌")

    token = auth_header[7:]
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        await blacklist_token(jti, exp)

    return {"message": "已成功注销"}


@router.get("/me", response_model=UserInfo)
async def get_profile(user: User = Depends(get_current_user)):
    return _user_info(user)


@router.put("/me", response_model=UserInfo)
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    if body.username and body.username != user.username:
        existing = await db.execute(
            select(User).where(User.username == body.username)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="用户名已被占用")
        user.username = body.username

    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url

    await db.commit()
    await db.refresh(user)
    return _user_info(user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"message": "密码修改成功"}
