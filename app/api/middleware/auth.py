from __future__ import annotations

import logging

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """API key authentication (rate limiting moved to slowapi)."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._available = redis_client is not None

    async def authenticate(self, request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(
                status_code=401, detail="Missing API key"
            )

        if not self._available:
            return api_key

        key_data = await self.redis.hgetall(f"apikey:{api_key}")
        if not key_data:
            raise HTTPException(
                status_code=401, detail="Invalid API key"
            )

        return api_key
