from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global _redis_client
    _redis_client = aioredis.from_url(
        settings.redis_url,
        decode_responses=False,
        max_connections=20,
    )
    await _redis_client.ping()
    logger.info("redis_connected url=%s", settings.redis_url)
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("redis_closed")


def get_redis() -> aioredis.Redis | None:
    return _redis_client
