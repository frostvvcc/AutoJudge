from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """
    API key authentication + three-tier rate limiting.
    Adversarial debate is compute-intensive (35s + $0.15/call),
    must rate-limit to prevent abuse.
    """

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

    async def check_rate_limit(self, api_key: str):
        if not self._available:
            return

        now = datetime.now(timezone.utc)
        limits = [
            (
                f"rate:{api_key}:min:{now.strftime('%Y%m%d%H%M')}",
                5,
                120,
            ),
            (
                f"rate:{api_key}:hour:{now.strftime('%Y%m%d%H')}",
                30,
                7200,
            ),
            (
                f"rate:{api_key}:day:{now.strftime('%Y%m%d')}",
                100,
                172800,
            ),
        ]

        for key, limit, ttl in limits:
            try:
                current = await self.redis.incr(key)
                if current == 1:
                    await self.redis.expire(key, ttl)
                if current > limit:
                    window = key.split(":")[2]
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded: {limit} requests per {window}",
                        headers={"Retry-After": str(ttl)},
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning("%s: %s", "rate_limit_check_failed", e)
