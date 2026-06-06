"""
Redis-backed JWT token blacklist for logout revocation.

When a user logs out, the token's `jti` (JWT ID) is added to Redis
with a TTL matching the token's remaining lifetime. Subsequent requests
with the same token are rejected during validation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.redis import get_redis

logger = logging.getLogger(__name__)

_BLACKLIST_PREFIX = "token_blacklist:"


async def blacklist_token(jti: str, exp: int | float) -> None:
    """Add a token's jti to the blacklist until it naturally expires."""
    redis = get_redis()
    if redis is None:
        logger.warning("Redis unavailable — token blacklist disabled")
        return

    now = datetime.now(timezone.utc).timestamp()
    ttl = int(exp - now)
    if ttl <= 0:
        return

    await redis.setex(f"{_BLACKLIST_PREFIX}{jti}", ttl, "1")


async def is_blacklisted(jti: str) -> bool:
    """Check if a token's jti is in the blacklist."""
    redis = get_redis()
    if redis is None:
        return False

    result = await redis.get(f"{_BLACKLIST_PREFIX}{jti}")
    return result is not None
