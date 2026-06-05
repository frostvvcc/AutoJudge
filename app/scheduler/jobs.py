"""
Scheduler — modeled after AutoResearch's 8-job Cron scheduler.

AutoResearch jobs adapted for AutoJudge:
  Job 1 (Heartbeat)      → not needed (single instance)
  Job 2 (Quota recovery)  → recover_cooldown_keys
  Job 3 (Preparing TTL)   → cleanup_stale_tasks
  Job 4 (Partition maint.) → not needed (no partitioning)
  Job 5 (Doc backup)      → not needed (no S3)
  Job 6 (Token cleanup)   → handled by key_pool auto-recovery
  Job 7 (Orphan sessions) → cleanup_orphan_sessions
  Job 8 (Metrics agg.)    → aggregate_metrics
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@scheduler.scheduled_job("interval", minutes=5, id="recover_cooldown_keys")
async def recover_cooldown_keys():
    from app.llm.key_pool import get_pool

    pool = get_pool()
    pool.recover_cooldowns()


@scheduler.scheduled_job("interval", minutes=10, id="cleanup_stale_tasks")
async def cleanup_stale_tasks():
    from app.db.engine import async_session
    from app.db.models import DebateSession

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)

    try:
        async with async_session() as db:
            from sqlalchemy import update
            stmt = (
                update(DebateSession)
                .where(
                    DebateSession.status.in_(["queued", "planning", "debating"]),
                    DebateSession.created_at < cutoff,
                )
                .values(status="failed", convergence_reason="超时自动标记失败")
            )
            result = await db.execute(stmt)
            await db.commit()
            if result.rowcount:
                logger.info("stale_tasks_cleaned count=%d", result.rowcount)
    except Exception as e:
        logger.warning("cleanup_stale_tasks_failed error=%s", e)


@scheduler.scheduled_job("interval", hours=1, id="aggregate_metrics")
async def aggregate_metrics():
    from app.llm.key_pool import get_pool

    pool = get_pool()
    status = pool.get_pool_status()
    total_tokens = sum(m["total_tokens"] for m in status)
    total_requests = sum(m["total_requests"] for m in status)
    logger.info(
        "metrics_aggregate keys=%d total_tokens=%d total_requests=%d",
        len(status), total_tokens, total_requests,
    )


@scheduler.scheduled_job("cron", hour=3, id="cleanup_orphan_sessions")
async def cleanup_orphan_sessions():
    from app.db.engine import async_session
    from app.db.models import DebateSession

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    try:
        async with async_session() as db:
            from sqlalchemy import delete
            stmt = (
                delete(DebateSession)
                .where(
                    DebateSession.status == "failed",
                    DebateSession.result_code.is_(None),
                    DebateSession.created_at < cutoff,
                )
            )
            result = await db.execute(stmt)
            await db.commit()
            if result.rowcount:
                logger.info("orphan_sessions_cleaned count=%d", result.rowcount)
    except Exception as e:
        logger.warning("cleanup_orphan_sessions_failed error=%s", e)
