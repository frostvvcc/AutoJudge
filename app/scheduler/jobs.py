"""
Scheduler — modeled after AutoResearch's 8-job Cron scheduler.

Adapted for AutoJudge:
  Job 1: cleanup_stale_tasks   (from AutoResearch Job 3: Preparing TTL)
  Job 2: aggregate_metrics     (from AutoResearch Job 8)
  Job 3: cleanup_orphan_sessions (from AutoResearch Job 7)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


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
    from app.db.engine import async_session
    from app.db.models import DebateSession
    from sqlalchemy import func, select

    try:
        async with async_session() as db:
            row = (await db.execute(
                select(
                    func.count(DebateSession.id),
                    func.sum(DebateSession.total_tokens),
                ).where(DebateSession.status == "completed")
            )).one()
            logger.info(
                "metrics_aggregate completed_sessions=%s total_tokens=%s",
                row[0], row[1],
            )
    except Exception as e:
        logger.warning("aggregate_metrics_failed error=%s", e)


@scheduler.scheduled_job("cron", hour=4, id="evict_memory")
async def evict_memory():
    """Evict excess records from ChromaDB collections to prevent unbounded growth."""
    from app.memory.attack_knowledge import AttackKnowledgeBase
    from app.memory.fix_patterns import FixPatternStore
    from app.memory.eviction import EvictionManager

    try:
        attack_kb = AttackKnowledgeBase()
        if attack_kb._available:
            await EvictionManager(attack_kb.collection).evict_if_needed()

        fix_store = FixPatternStore()
        if fix_store._available:
            await EvictionManager(fix_store.collection).evict_if_needed()

        await attack_kb.check_distribution()
    except Exception as e:
        logger.warning("evict_memory_failed error=%s", e)


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
