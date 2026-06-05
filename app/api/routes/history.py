from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.deps import get_current_user
from app.db.engine import get_session
from app.db.models import DebateMessage, DebateSession, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/history", tags=["history"])


# ---------- Response schemas ----------

class SessionBrief(BaseModel):
    sid: str
    task: str
    language: str
    status: str
    converged: bool
    confidence: float
    total_rounds: int
    total_tokens: int
    cost_usd: float
    created_at: datetime
    finished_at: datetime | None


class MessageOut(BaseModel):
    agent: str
    content: str
    round: int
    code: str | None
    structured_json: dict | None


class SessionDetail(BaseModel):
    sid: str
    task: str
    language: str
    framework: str | None
    config_json: dict
    status: str
    result_code: str | None
    confidence: float
    converged: bool
    convergence_reason: str | None
    summary_json: dict | None
    risk_json: dict | None
    metrics_json: dict | None
    quality_report_json: dict | None
    total_rounds: int
    total_tokens: int
    total_latency_ms: int
    cost_usd: float
    created_at: datetime
    finished_at: datetime | None
    messages: list[MessageOut]


class PaginatedHistory(BaseModel):
    items: list[SessionBrief]
    total: int
    page: int
    page_size: int
    total_pages: int


class StatsOut(BaseModel):
    total_sessions: int
    total_tokens: int
    total_cost_usd: float
    languages: dict[str, int]
    avg_confidence: float
    converge_rate: float


# ---------- Endpoints ----------

@router.get("", response_model=PaginatedHistory)
async def list_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    language: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    query = select(DebateSession).where(DebateSession.user_id == user.id)

    if language:
        query = query.where(DebateSession.language == language)
    if status:
        query = query.where(DebateSession.status == status)
    if search:
        query = query.where(DebateSession.task.contains(search))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    total_pages = max(1, (total + page_size - 1) // page_size)

    query = query.order_by(desc(DebateSession.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    sessions = result.scalars().all()

    items = [
        SessionBrief(
            sid=s.sid,
            task=s.task,
            language=s.language,
            status=s.status,
            converged=s.converged,
            confidence=s.confidence,
            total_rounds=s.total_rounds,
            total_tokens=s.total_tokens,
            cost_usd=s.cost_usd,
            created_at=s.created_at,
            finished_at=s.finished_at,
        )
        for s in sessions
    ]

    return PaginatedHistory(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=StatsOut)
async def get_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    base = select(DebateSession).where(DebateSession.user_id == user.id)
    result = await db.execute(base)
    sessions = result.scalars().all()

    if not sessions:
        return StatsOut(
            total_sessions=0,
            total_tokens=0,
            total_cost_usd=0.0,
            languages={},
            avg_confidence=0.0,
            converge_rate=0.0,
        )

    languages: dict[str, int] = {}
    total_tokens = 0
    total_cost = 0.0
    total_conf = 0.0
    converged_count = 0

    for s in sessions:
        languages[s.language] = languages.get(s.language, 0) + 1
        total_tokens += s.total_tokens
        total_cost += s.cost_usd
        total_conf += s.confidence
        if s.converged:
            converged_count += 1

    n = len(sessions)
    return StatsOut(
        total_sessions=n,
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 4),
        languages=languages,
        avg_confidence=round(total_conf / n, 3) if n else 0.0,
        converge_rate=round(converged_count / n, 3) if n else 0.0,
    )


@router.get("/{sid}", response_model=SessionDetail)
async def get_session_detail(
    sid: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(DebateSession)
        .options(selectinload(DebateSession.messages))
        .where(DebateSession.sid == sid, DebateSession.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="记录不存在")

    return SessionDetail(
        sid=session.sid,
        task=session.task,
        language=session.language,
        framework=session.framework,
        config_json=session.config_json,
        status=session.status,
        result_code=session.result_code,
        confidence=session.confidence,
        converged=session.converged,
        convergence_reason=session.convergence_reason,
        summary_json=session.summary_json,
        risk_json=session.risk_json,
        metrics_json=session.metrics_json,
        quality_report_json=session.quality_report_json,
        total_rounds=session.total_rounds,
        total_tokens=session.total_tokens,
        total_latency_ms=session.total_latency_ms,
        cost_usd=session.cost_usd,
        created_at=session.created_at,
        finished_at=session.finished_at,
        messages=[
            MessageOut(
                agent=m.agent,
                content=m.content,
                round=m.round,
                code=m.code,
                structured_json=m.structured_json,
            )
            for m in session.messages
        ],
    )


@router.delete("/{sid}")
async def delete_session(
    sid: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(DebateSession).where(
            DebateSession.sid == sid, DebateSession.user_id == user.id
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="记录不存在")

    await db.delete(session)
    await db.commit()
    return {"message": "删除成功"}
