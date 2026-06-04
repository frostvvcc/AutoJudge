from __future__ import annotations

from app.config import settings

MODEL_ROUTING = {
    "requirement_parser": settings.haiku_model,
    "coder": settings.default_model,
    "security": settings.default_model,
    "performance": settings.default_model,
    "correctness": settings.default_model,
    "cross_review": settings.haiku_model,
    "compressor": settings.haiku_model,
    "judge": settings.default_model,
    "test_generator": settings.haiku_model,
    "arbitrator": settings.default_model,
    "planner": settings.haiku_model,
}


def get_model_for_agent(agent: str) -> str:
    return MODEL_ROUTING.get(agent, settings.default_model)
