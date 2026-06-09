from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

MODEL_ROUTING = {
    # Haiku: lightweight tasks where speed matters more than depth
    "planner": settings.haiku_model,
    "cross_review": settings.haiku_model,
    "compressor": settings.haiku_model,
    "test_generator": settings.haiku_model,
    "requirement_parser": settings.haiku_model,

    # Opus: tasks requiring deep analysis, reliable tool_use, or multi-dimensional reasoning
    "coder": settings.default_model,
    "security": settings.default_model,
    "performance": settings.default_model,
    "correctness": settings.default_model,
    "judge": settings.default_model,
    "arbitrator": settings.default_model,
}


def get_model_for_agent(agent: str) -> str:
    model = MODEL_ROUTING.get(agent)
    if model is None:
        logger.warning("model_routing_fallback agent=%s using default=%s", agent, settings.default_model)
        return settings.default_model
    return model
