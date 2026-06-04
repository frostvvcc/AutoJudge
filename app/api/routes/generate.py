from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from app.api.models.request import GenerateRequest
from app.api.models.response import DebateResult
from app.engine.context import DebateConfig
from app.engine.degradation import DegradationManager
from app.engine.resource_manager import ResourceManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["generate"])

degradation_mgr = DegradationManager()
resource_mgr = ResourceManager()


@router.post("/generate", response_model=DebateResult)
async def generate(request: GenerateRequest, raw_request: Request):
    config = DebateConfig(
        max_rounds=request.config.max_rounds if request.config else 5,
        attackers=(
            request.config.attackers
            if request.config
            else ["security", "performance", "correctness"]
        ),
        model=(
            request.config.model
            if request.config
            else "claude-sonnet-4-20250514"
        ),
        max_tokens=(
            request.config.max_tokens if request.config else 100_000
        ),
    )

    api_key = getattr(raw_request.state, "api_key", None)

    async with resource_mgr.acquire_debate_slot():
        result = await degradation_mgr.execute_with_degradation(
            requirement=request.task,
            language=request.language,
            framework=request.framework,
            config=config,
            api_key=api_key,
        )

    return result


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

    task = init_msg.get("task", "")
    language = init_msg.get("language", "python")
    framework = init_msg.get("framework")
    api_key = init_msg.get("api_key")

    config_data = init_msg.get("config", {})
    config = DebateConfig(
        max_rounds=config_data.get("max_rounds", 5),
        attackers=config_data.get(
            "attackers", ["security", "performance", "correctness"]
        ),
        model=config_data.get("model", "claude-sonnet-4-20250514"),
        max_tokens=config_data.get("max_tokens", 100_000),
    )

    from app.engine.orchestrator import DebateOrchestrator
    orchestrator = DebateOrchestrator()

    stop_event = asyncio.Event()
    debate_task: asyncio.Task | None = None

    async def listen_for_intervention():
        nonlocal debate_task
        while not stop_event.is_set():
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(), timeout=1.0
                )
                msg_type = msg.get("type")
                if msg_type == "skip_attacker":
                    attacker = msg.get("attacker", "")
                    if attacker in ("security", "performance", "correctness"):
                        config.attackers = [
                            a for a in config.attackers if a != attacker
                        ]
                        logger.info("user_skipped_attacker attacker=%s", attacker)
                elif msg_type == "add_context":
                    extra = msg.get("content", "")
                    if extra:
                        # Write to the DebateContext that orchestrator
                        # actually reads during Coder prompt construction
                        orchestrator._live_extra_context = extra
                        logger.info("user_added_context")
                elif msg_type == "force_stop":
                    stop_event.set()
                    if debate_task and not debate_task.done():
                        debate_task.cancel()
                    logger.info("user_forced_stop")
            except asyncio.TimeoutError:
                continue
            except (WebSocketDisconnect, Exception):
                break

    async def on_progress(event: dict):
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    try:
        async with asyncio.timeout(300):
            listener_task = asyncio.create_task(listen_for_intervention())

            async def run_debate():
                return await orchestrator.run(
                    requirement=task,
                    language=language,
                    framework=framework,
                    config=config,
                    on_progress=on_progress,
                    api_key=api_key,
                )

            debate_task = asyncio.create_task(run_debate())
            try:
                result = await debate_task
            except asyncio.CancelledError:
                result = DebateResult(
                    code="",
                    language=language,
                    convergence_reason="用户手动终止",
                )
            finally:
                stop_event.set()
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass

        await websocket.send_json({
            "type": "result",
            "data": result.model_dump(),
        })

    except asyncio.TimeoutError:
        await websocket.send_json({
            "type": "error", "message": "Session timeout (5 min)"
        })
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
