"""
API Key Pool — modeled after AutoResearch's Claude AI Pool.

Core strategies preserved from AutoResearch:
  - Quota tracking with sliding windows (1-min RPM, 1-min TPM, daily)
  - Sticky Session (same debate reuses the same key)
  - Exponential backoff on 429 → Cooldown → automatic recovery
  - Encrypted credential storage (Fernet instead of KMS)

Downgrade from AutoResearch:
  - OAuth Token → API Key (official Anthropic API)
  - Aurora + Redis ZSET → MySQL + in-memory counters
  - N subscription accounts → N API keys across accounts
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_pool: APIKeyPool | None = None


@dataclass
class PoolMember:
    id: int
    name: str
    backend: str
    decrypted_key: str
    base_url: str | None
    rpm_limit: int
    tpm_limit: int
    daily_token_limit: int
    status: str = "active"
    cooldown_until: float = 0.0

    _request_timestamps: list[float] = field(default_factory=list)
    _token_counts: list[tuple[float, int]] = field(default_factory=list)
    _daily_tokens: int = 0
    _daily_reset_at: float = 0.0
    _sticky_session: str | None = None
    _total_tokens_used: int = 0
    _total_requests: int = 0

    @property
    def rpm_used(self) -> int:
        cutoff = time.time() - 60
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
        return len(self._request_timestamps)

    @property
    def tpm_used(self) -> int:
        cutoff = time.time() - 60
        self._token_counts = [(t, n) for t, n in self._token_counts if t > cutoff]
        return sum(n for _, n in self._token_counts)

    @property
    def quota_remaining(self) -> float:
        rpm_ratio = 1 - (self.rpm_used / max(self.rpm_limit, 1))
        tpm_ratio = 1 - (self.tpm_used / max(self.tpm_limit, 1))
        daily_ratio = 1 - (self._daily_tokens / max(self.daily_token_limit, 1))
        return min(rpm_ratio, tpm_ratio, daily_ratio)

    def is_available(self) -> bool:
        if self.status == "disabled":
            return False
        if self.status == "cooldown":
            if time.time() > self.cooldown_until:
                self.status = "active"
            else:
                return False
        return self.quota_remaining > 0.05

    def record_usage(self, tokens: int):
        now = time.time()
        self._request_timestamps.append(now)
        self._token_counts.append((now, tokens))
        self._total_tokens_used += tokens
        self._total_requests += 1
        if now > self._daily_reset_at:
            self._daily_tokens = 0
            self._daily_reset_at = now + 86400
        self._daily_tokens += tokens

    def enter_cooldown(self, seconds: int = 300):
        self.status = "cooldown"
        self.cooldown_until = time.time() + seconds
        logger.warning("key_cooldown name=%s seconds=%d", self.name, seconds)


class PoolExhausted(Exception):
    pass


class APIKeyPool:

    def __init__(self):
        self.members: dict[int, PoolMember] = {}
        self._lock = asyncio.Lock()

    async def load_from_db(self, db: AsyncSession):
        from app.db.models import APIKeyPoolRecord
        from app.security.credential_manager import get_credential_manager

        cm = get_credential_manager()
        result = await db.execute(
            select(APIKeyPoolRecord).where(APIKeyPoolRecord.status != "disabled")
        )
        rows = result.scalars().all()

        for row in rows:
            try:
                decrypted = cm.decrypt(row.encrypted_key)
            except ValueError:
                logger.error("key_decrypt_failed id=%d name=%s", row.id, row.name)
                continue

            self.members[row.id] = PoolMember(
                id=row.id,
                name=row.name,
                backend=row.backend,
                decrypted_key=decrypted,
                base_url=row.base_url,
                rpm_limit=row.rpm_limit,
                tpm_limit=row.tpm_limit,
                daily_token_limit=row.daily_token_limit,
                status=row.status if row.status != "cooldown" else "active",
            )
        logger.info("key_pool_loaded count=%d", len(self.members))

    def load_from_env(self):
        """Fallback: load from env vars when no DB records exist."""
        from app.config import settings

        member_id = 1
        if settings.anthropic_proxy_base_url and settings.anthropic_proxy_api_key:
            self.members[member_id] = PoolMember(
                id=member_id,
                name="env-proxy",
                backend="anthropic_proxy",
                decrypted_key=settings.anthropic_proxy_api_key,
                base_url=settings.anthropic_proxy_base_url,
                rpm_limit=50,
                tpm_limit=200000,
                daily_token_limit=2000000,
            )
            member_id += 1

        if settings.anthropic_api_key:
            self.members[member_id] = PoolMember(
                id=member_id,
                name="env-direct",
                backend="anthropic_api",
                decrypted_key=settings.anthropic_api_key,
                base_url=None,
                rpm_limit=50,
                tpm_limit=100000,
                daily_token_limit=1000000,
            )

        if self.members:
            logger.info("key_pool_loaded_from_env count=%d", len(self.members))

    async def acquire(self, session_id: str | None = None) -> PoolMember:
        async with self._lock:
            if session_id:
                for m in self.members.values():
                    if m._sticky_session == session_id and m.is_available():
                        return m

            available = [m for m in self.members.values() if m.is_available()]
            if not available:
                cooldowns = [
                    m for m in self.members.values() if m.status == "cooldown"
                ]
                if cooldowns:
                    nearest = min(cooldowns, key=lambda m: m.cooldown_until)
                    wait = max(0, nearest.cooldown_until - time.time())
                    raise PoolExhausted(
                        f"所有 Key 冷却中，最快 {int(wait)}s 后恢复 ({nearest.name})"
                    )
                raise PoolExhausted("没有可用的 API Key")

            best = max(available, key=lambda m: m.quota_remaining)

            if session_id:
                best._sticky_session = session_id

            return best

    async def release(self, member: PoolMember, tokens_used: int):
        async with self._lock:
            member.record_usage(tokens_used)

    async def handle_rate_limit(self, member: PoolMember, retry_after: int = 60):
        async with self._lock:
            member.enter_cooldown(retry_after)

    def recover_cooldowns(self):
        now = time.time()
        for m in self.members.values():
            if m.status == "cooldown" and now > m.cooldown_until:
                m.status = "active"
                logger.info("key_recovered name=%s", m.name)

    def get_pool_status(self) -> list[dict]:
        return [
            {
                "name": m.name,
                "backend": m.backend,
                "status": m.status,
                "quota_remaining": round(m.quota_remaining, 2),
                "rpm_used": m.rpm_used,
                "tpm_used": m.tpm_used,
                "daily_tokens": m._daily_tokens,
                "total_tokens": m._total_tokens_used,
                "total_requests": m._total_requests,
                "cooldown_until": m.cooldown_until if m.status == "cooldown" else None,
            }
            for m in self.members.values()
        ]


def get_pool() -> APIKeyPool:
    global _pool
    if _pool is None:
        _pool = APIKeyPool()
    return _pool


async def init_pool(db: AsyncSession | None = None):
    pool = get_pool()
    if db:
        await pool.load_from_db(db)
    if not pool.members:
        pool.load_from_env()
    if not pool.members:
        logger.error("key_pool_empty — no API keys available")
