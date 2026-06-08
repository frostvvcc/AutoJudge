import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models.request import GenerateRequest
from app.api.models.response import DebateResult
from app.api.middleware.rate_limit import limiter
from app.auth.deps import get_current_user
from app.auth.jwt import decode_token
from app.db.engine import async_session
from app.db.models import DebateMessage as DBMessage, DebateSession, DebateStatus, User
from app.engine.context import DebateConfig
from app.engine.degradation import DegradationManager
from app.engine.resource_manager import ResourceManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["generate"])


def _compute_session_timeout(config: DebateConfig) -> int:
    """Compute WebSocket/REST session timeout based on debate configuration.

    Models the expected wall-clock time as:
      per_round = coder_call + max(parallel_attackers) + cross_review
      total = rounds * per_round + overhead(requirement_parse + test_runner + judge)
    Then adds a 60% buffer for network/scheduling variance.
    """
    agent_call_seconds = 40
    per_round = agent_call_seconds + (
        max(len(config.attackers) * agent_call_seconds, agent_call_seconds)
    ) + (agent_call_seconds if not config.skip_cross_review else 0)
    overhead = agent_call_seconds * 3
    return int((config.max_rounds * per_round + overhead) * 1.6)

degradation_mgr = DegradationManager()
resource_mgr = ResourceManager()


def _build_partial_result(
    collected_messages: list[dict], language: str, reason: str
) -> DebateResult:
    """Recover whatever the debate produced before interruption/timeout.

    Scans collected messages for the last Coder code submission so the
    user gets something useful instead of an empty string.
    """
    last_code = ""
    for msg in reversed(collected_messages):
        if msg.get("agent") == "coder" and msg.get("code"):
            last_code = msg["code"]
            break

    rounds: dict[int, list[dict]] = {}
    for msg in collected_messages:
        r = msg.get("round", 0)
        rounds.setdefault(r, []).append({
            "agent": msg.get("agent", "?"),
            "content": msg.get("content", ""),
            "code": msg.get("code"),
        })
    transcript = [
        {"round": r, "messages": msgs}
        for r, msgs in sorted(rounds.items())
    ]

    return DebateResult(
        code=last_code,
        language=language,
        debate={
            "total_rounds": max(rounds.keys()) if rounds else 0,
            "converged": False,
            "consensus_reason": reason,
            "transcript": transcript,
        },
        convergence_reason=reason,
        metadata={"partial": True},
    )


async def _save_session(
    user_id: int,
    task: str,
    language: str,
    framework: str | None,
    config: DebateConfig,
    result: DebateResult,
    messages: list[dict],
) -> str:
    async with async_session() as db:
        session = DebateSession(
            user_id=user_id,
            task=task,
            language=language,
            framework=framework,
            config_json={
                "mode": config.mode,
                "max_rounds": config.max_rounds,
                "attackers": config.attackers,
                "model": config.model,
                "max_tokens": config.max_tokens,
            },
            status=(
                DebateStatus.COMPLETED.value
                if result.code
                else DebateStatus.FAILED.value
            ),
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
        db.add(session)
        await db.flush()

        for msg in messages:
            db.add(DBMessage(
                session_id=session.id,
                agent=msg.get("agent", "system"),
                content=msg.get("content", ""),
                round=msg.get("round", 0),
                code=msg.get("code"),
                structured_json=msg.get("structured"),
            ))

        await db.commit()
        await db.refresh(session)
        return session.sid


@router.post("/generate", response_model=DebateResult)
@limiter.limit("5/minute;30/hour;100/day")
async def generate(
    request: Request,
    body: GenerateRequest,
    user: User = Depends(get_current_user),
):
    config = DebateConfig(
        mode=body.config.mode if body.config else "pro",
        max_rounds=body.config.max_rounds if body.config else 5,
        attackers=(
            body.config.attackers
            if body.config
            else ["security", "performance", "correctness"]
        ),
        model=(
            body.config.model
            if body.config
            else "claude-sonnet-4-20250514"
        ),
        max_tokens=(
            body.config.max_tokens if body.config else DebateConfig().max_tokens
        ),
    )

    collected_messages: list[dict] = []

    async def collect_progress(event: dict):
        if event.get("type") == "message":
            collected_messages.append(event)

    async with resource_mgr.acquire_debate_slot():
        result = await degradation_mgr.execute_with_degradation(
            requirement=body.task,
            language=body.language,
            framework=body.framework,
            config=config,
            api_key=None,
            on_progress=collect_progress,
        )

    await _save_session(
        user_id=user.id,
        task=body.task,
        language=body.language,
        framework=body.framework,
        config=config,
        result=result,
        messages=collected_messages,
    )

    return result


@router.post("/generate/async")
@limiter.limit("5/minute;30/hour;100/day")
async def generate_async(
    request: Request,
    body: GenerateRequest,
    user: User = Depends(get_current_user),
):
    """Enqueue a debate task for async processing via arq worker."""
    config = DebateConfig(
        mode=body.config.mode if body.config else "pro",
        max_rounds=body.config.max_rounds if body.config else 5,
        attackers=(
            body.config.attackers
            if body.config
            else ["security", "performance", "correctness"]
        ),
        model=(
            body.config.model
            if body.config
            else "claude-sonnet-4-20250514"
        ),
        max_tokens=(
            body.config.max_tokens if body.config else DebateConfig().max_tokens
        ),
    )

    task_id = uuid.uuid4().hex

    async with async_session() as db:
        session = DebateSession(
            sid=task_id,
            user_id=user.id,
            task=body.task,
            language=body.language,
            framework=body.framework,
            config_json={
                "mode": config.mode,
                "max_rounds": config.max_rounds,
                "attackers": config.attackers,
                "model": config.model,
                "max_tokens": config.max_tokens,
            },
            status=DebateStatus.QUEUED.value,
        )
        db.add(session)
        await db.commit()

    try:
        from arq import create_pool as arq_create_pool
        from app.queue.worker import _parse_redis_url
        from app.config import settings as _settings

        redis_pool = await arq_create_pool(_parse_redis_url(_settings.redis_url))
        await redis_pool.enqueue_job(
            "run_debate_task",
            task_id,
            body.task,
            body.language,
            body.framework,
            {
                "max_rounds": config.max_rounds,
                "attackers": config.attackers,
                "model": config.model,
                "max_tokens": config.max_tokens,
            },
            user.id,
        )
        await redis_pool.close()
    except Exception as e:
        logger.warning("arq_enqueue_failed error=%s, falling back to sync", e)
        return await generate(request, body, user)

    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}")
async def get_task_status(
    task_id: str,
    user: User = Depends(get_current_user),
):
    """Poll task status for async-enqueued debates."""
    async with async_session() as db:
        result = await db.execute(
            select(DebateSession).where(
                DebateSession.sid == task_id,
                DebateSession.user_id == user.id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Task not found")

        response = {
            "task_id": task_id,
            "status": session.status,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        }

        if session.status == DebateStatus.COMPLETED.value:
            response["result_code"] = session.result_code
            response["confidence"] = session.confidence
            response["converged"] = session.converged
            response["metrics"] = session.metrics_json
            response["quality_report"] = session.quality_report_json

        return response


@router.websocket("/ws/generate")
async def websocket_generate(websocket: WebSocket):
    await websocket.accept()

    try:
        init_msg = await asyncio.wait_for(
            websocket.receive_json(), timeout=10
        )
    except asyncio.TimeoutError:
        await websocket.close(code=4000, reason="Authentication timeout")
        return

    user_id: int | None = None
    token = init_msg.get("token")
    if token:
        payload = decode_token(token)
        if payload and payload.get("type") == "access":
            user_id = int(payload["sub"])

    task = init_msg.get("task", "")
    language = init_msg.get("language", "python")
    framework = init_msg.get("framework")

    config_data = init_msg.get("config", {})
    config = DebateConfig(
        mode=config_data.get("mode", "pro"),
        max_rounds=config_data.get("max_rounds", 5),
        attackers=config_data.get(
            "attackers", ["security", "performance", "correctness"]
        ),
        model=config_data.get("model", "claude-sonnet-4-20250514"),
        max_tokens=config_data.get("max_tokens", 100_000),
    )

    stop_event = asyncio.Event()
    debate_task: asyncio.Task | None = None
    collected_messages: list[dict] = []

    interrupt_queue: asyncio.Queue = asyncio.Queue()

    async def listen_for_intervention():
        nonlocal debate_task
        while not stop_event.is_set():
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(), timeout=1.0
                )
                msg_type = msg.get("type")
                if msg_type == "force_stop":
                    stop_event.set()
                    if debate_task and not debate_task.done():
                        debate_task.cancel()
                    logger.info("user_forced_stop")
                elif msg_type == "interrupt_response":
                    await interrupt_queue.put(msg.get("data", {}))
            except asyncio.TimeoutError:
                continue
            except (WebSocketDisconnect, Exception):
                break

    async def handle_interrupt(payload: dict) -> dict:
        """Send interrupt to frontend, wait for user response or timeout."""
        try:
            await websocket.send_json({"type": "interrupt", "payload": payload})
        except Exception:
            return {}
        try:
            return await asyncio.wait_for(interrupt_queue.get(), timeout=120)
        except asyncio.TimeoutError:
            return {}

    async def on_progress(event: dict):
        if event.get("type") == "message":
            collected_messages.append(event)
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    session_timeout = _compute_session_timeout(config)

    try:
        async with asyncio.timeout(session_timeout):
            listener_task = asyncio.create_task(listen_for_intervention())

            async def run_debate():
                return await degradation_mgr.execute_with_degradation(
                    requirement=task,
                    language=language,
                    framework=framework,
                    config=config,
                    on_progress=on_progress,
                    api_key=None,
                    interrupt_handler=handle_interrupt,
                )

            debate_task = asyncio.create_task(run_debate())
            try:
                result = await debate_task
            except asyncio.CancelledError:
                result = _build_partial_result(
                    collected_messages, language, "用户手动终止"
                )
            finally:
                stop_event.set()
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass

        session_sid = None
        if user_id:
            try:
                session_sid = await _save_session(
                    user_id=user_id,
                    task=task,
                    language=language,
                    framework=framework,
                    config=config,
                    result=result,
                    messages=collected_messages,
                )
            except Exception as e:
                logger.error("save_session_failed error=%s", e)

        await websocket.send_json({
            "type": "result",
            "data": result.model_dump(),
            "session_sid": session_sid,
        })

    except asyncio.TimeoutError:
        result = _build_partial_result(
            collected_messages, language,
            f"会话超时（{session_timeout}s），返回已完成的部分结果",
        )
        try:
            await websocket.send_json({
                "type": "result",
                "data": result.model_dump(),
                "partial": True,
            })
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info("websocket_disconnected")
    except Exception as e:
        logger.error("websocket_error error=%s", e)
        try:
            await websocket.send_json({
                "type": "error", "message": str(e)
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
