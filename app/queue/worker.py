"""
Task queue worker — modeled after AutoResearch's SQS FIFO + BE Nodes.

Downgrade: SQS FIFO → arq (Redis-backed async task queue).
Same pattern: API enqueues → Worker consumes → result saved + WS notified.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings

logger = logging.getLogger(__name__)


async def run_debate_task(
    ctx: dict,
    task_id: str,
    requirement: str,
    language: str,
    framework: str | None,
    config_dict: dict,
    user_id: int | None = None,
):
    """Worker function: runs a full debate and persists results."""
    from app.engine.graph import run_debate_with_graph
    from app.engine.context import DebateConfig
    from app.db.engine import async_session
    from app.db.models import DebateSession, DebateMessage as DBMessage

    config = DebateConfig(
        mode=config_dict.get("mode", "pro"),
        max_rounds=config_dict.get("max_rounds", 5),
        attackers=config_dict.get("attackers", ["security", "performance", "correctness"]),
        model=config_dict.get("model", "claude-sonnet-4-20250514"),
        max_tokens=config_dict.get("max_tokens", 100_000),
    )

    async with async_session() as db:
        from sqlalchemy import update
        await db.execute(
            update(DebateSession)
            .where(DebateSession.sid == task_id)
            .values(status="debating")
        )
        await db.commit()

    collected_messages: list[dict] = []

    async def collect_progress(event: dict):
        if event.get("type") == "message":
            collected_messages.append(event)
        if event.get("type") == "phase_change":
            phase = event.get("phase", "debating")
            status_map = {
                "plan": "planning",
                "arbitration": "arbitrating",
                "fix": "fixing",
            }
            new_status = status_map.get(phase, "debating")
            async with async_session() as db:
                await db.execute(
                    update(DebateSession)
                    .where(DebateSession.sid == task_id)
                    .values(status=new_status)
                )
                await db.commit()

    try:
        result = await run_debate_with_graph(
            requirement=requirement,
            language=language,
            framework=framework,
            config=config,
            on_progress=collect_progress,
        )

        async with async_session() as db:
            from sqlalchemy import update as sql_update
            await db.execute(
                sql_update(DebateSession)
                .where(DebateSession.sid == task_id)
                .values(
                    status="completed",
                    result_code=result.code or None,
                    confidence=result.confidence,
                    converged=result.converged,
                    convergence_reason=result.convergence_reason or None,
                    summary_json=result.summary.model_dump() if result.summary else None,
                    risk_json=result.risk_assessment.model_dump() if result.risk_assessment else None,
                    quality_report_json=result.quality_report.model_dump() if result.quality_report else None,
                    metrics_json=result.metrics.model_dump() if result.metrics else None,
                    total_rounds=result.metrics.total_rounds if result.metrics else 0,
                    total_tokens=result.metrics.total_tokens if result.metrics else 0,
                    total_latency_ms=result.metrics.total_latency_ms if result.metrics else 0,
                    cost_usd=result.metrics.cost_usd if result.metrics else 0.0,
                    finished_at=datetime.now(timezone.utc),
                )
            )

            for msg in collected_messages:
                from sqlalchemy import select
                sess_row = (await db.execute(
                    select(DebateSession.id).where(DebateSession.sid == task_id)
                )).scalar_one()
                db.add(DBMessage(
                    session_id=sess_row,
                    agent=msg.get("agent", "system"),
                    content=msg.get("content", ""),
                    round=msg.get("round", 0),
                    code=msg.get("code"),
                    structured_json=msg.get("structured"),
                ))

            await db.commit()

        logger.info("debate_task_completed task_id=%s", task_id)
        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        logger.error("debate_task_failed task_id=%s error=%s", task_id, e)
        async with async_session() as db:
            from sqlalchemy import update as sql_update
            await db.execute(
                sql_update(DebateSession)
                .where(DebateSession.sid == task_id)
                .values(status="failed", convergence_reason=str(e)[:255])
            )
            await db.commit()
        raise


def _parse_redis_url(url: str) -> RedisSettings:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or "0"),
        password=parsed.password,
    )


class WorkerSettings:
    functions = [run_debate_task]
    redis_settings = _parse_redis_url(settings.redis_url)
    max_jobs = settings.max_concurrent_debates
    job_timeout = 4500
