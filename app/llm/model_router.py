from __future__ import annotations

from app.config import settings

MODEL_ROUTING = {
    "requirement_parser": settings.haiku_model,
    "coder": settings.haiku_model,
    "security": settings.haiku_model,
    "performance": settings.haiku_model,
    "correctness": settings.haiku_model,
    "cross_review": settings.haiku_model,
    "compressor": settings.haiku_model,
    "judge": settings.haiku_model,
    "test_generator": settings.haiku_model,
    "arbitrator": settings.haiku_model,
    "planner": settings.haiku_model,
}


def get_model_for_agent(agent: str) -> str:
    return MODEL_ROUTING.get(agent, settings.default_model)
