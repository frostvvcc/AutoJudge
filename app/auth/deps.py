from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.blacklist import is_blacklisted
from app.auth.jwt import decode_token
from app.db.engine import get_session
from app.db.models import User


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少认证令牌")

    token = auth_header[7:]
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="令牌无效或已过期")

    jti = payload.get("jti")
    if jti and await is_blacklisted(jti):
        raise HTTPException(status_code=401, detail="令牌已注销")

    user_id = int(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return user
