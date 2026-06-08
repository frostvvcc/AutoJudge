from __future__ import annotations

import hashlib
import json
import math
import time
import logging

from app.api.models.response import DebateResult

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class ResultCache:
    """
    Embedding-similarity based result cache.
    "实现用户注册接口" and "写一个注册 API" are the same task;
    the second request doesn't need another 35s debate.
    """

    def __init__(
        self,
        redis_client=None,
        embedding_client=None,
        similarity_threshold: float = 0.92,
    ):
        self.redis = redis_client
        self.embedding = embedding_client
        self.similarity_threshold = similarity_threshold
        self._available = redis_client is not None

    async def get_cached(
        self, requirement: str, language: str
    ) -> DebateResult | None:
        if not self._available:
            return None

        try:
            query_vec = await self._embed(requirement)
            if query_vec is None:
                return None

            cache_keys = await self.redis.zrevrangebyscore(
                f"cache:index:{language}",
                "+inf",
                "-inf",
                start=0,
                num=50,
            )

            best_match = None
            best_score = 0.0

            for key in cache_keys:
                key_str = (
                    key.decode() if isinstance(key, bytes) else key
                )
                cached_vec_raw = await self.redis.get(
                    f"cache:vec:{key_str}"
                )
                if cached_vec_raw is None:
                    continue
                cached_vec = json.loads(cached_vec_raw)
                score = cosine_similarity(query_vec, cached_vec)
                if score > best_score:
                    best_score = score
                    best_match = key_str

            if best_match and best_score >= self.similarity_threshold:
                cached_data = await self.redis.get(
                    f"cache:result:{best_match}"
                )
                if cached_data:
                    data = (
                        cached_data.decode()
                        if isinstance(cached_data, bytes)
                        else cached_data
                    )
                    result = DebateResult.model_validate_json(data)
                    result.metadata["from_cache"] = True
                    result.metadata["cache_similarity"] = round(
                        best_score, 3
                    )
                    return result

            return None
        except Exception as e:
            logger.warning("%s: %s", "cache_get_failed", e)
            return None

    async def store(
        self,
        requirement: str,
        language: str,
        result: DebateResult,
    ):
        if not self._available:
            return

        try:
            cache_key = hashlib.sha256(
                f"{requirement}:{language}".encode()
            ).hexdigest()[:16]

            vec = await self._embed(requirement)
            if vec is None:
                return

            pipe = self.redis.pipeline()
            pipe.set(
                f"cache:result:{cache_key}",
                result.model_dump_json(),
                ex=86400,
            )
            pipe.set(
                f"cache:vec:{cache_key}",
                json.dumps(vec),
                ex=86400,
            )
            pipe.zadd(
                f"cache:index:{language}",
                {cache_key: time.time()},
            )
            await pipe.execute()
        except Exception as e:
            logger.warning("%s: %s", "cache_store_failed", e)

    def set_redis(self, redis_client):
        self.redis = redis_client
        self._available = redis_client is not None

    async def _embed(self, text: str) -> list[float] | None:
        if self.embedding is None:
            return None
        try:
            response = await self.embedding.embeddings.create(
                model="text-embedding-3-small", input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("%s: %s", "embedding_failed", e)
            return None


result_cache = ResultCache()
