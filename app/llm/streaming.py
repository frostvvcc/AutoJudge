from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def format_ws_event(event: dict) -> str:
    """Format a progress event for WebSocket transmission."""
    return json.dumps(event, ensure_ascii=False)


def format_agent_message(
    agent: str, content: str, code: str | None = None
) -> dict:
    event = {
        "type": "message",
        "agent": agent,
        "content": content,
    }
    if code:
        event["code"] = code
    return event


def format_round_start(round_num: int) -> dict:
    return {"type": "round_start", "round": round_num}


def format_convergence(
    round_num: int, reason: str
) -> dict:
    return {
        "type": "converged",
        "round": round_num,
        "reason": reason,
    }
