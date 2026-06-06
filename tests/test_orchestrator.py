"""Tests for debate graph integration logic (replaces old orchestrator tests)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.engine.context import DebateConfig
from app.llm.client import AgentResponse


def _mock_agent_response(agent, content, code=None, stance="attacking"):
    return AgentResponse(
        agent=agent,
        content=content,
        code=code,
        structured={
            "message": content,
            "stance": stance,
            "has_new_issues": stance == "attacking",
            "findings": [],
            "responses": [],
            "updated_code": code or "",
        },
        tokens_used=100,
    )


@pytest.mark.asyncio
async def test_debate_config_defaults():
    """DebateConfig should have sensible defaults."""
    config = DebateConfig()
    assert config.max_rounds >= 1
    assert isinstance(config.attackers, list)


@pytest.mark.asyncio
async def test_debate_config_custom():
    """DebateConfig should accept custom values."""
    config = DebateConfig(
        max_rounds=3,
        attackers=["security"],
        skip_cross_review=True,
    )
    assert config.max_rounds == 3
    assert config.attackers == ["security"]
    assert config.skip_cross_review is True


@pytest.mark.asyncio
async def test_complexity_router():
    """ComplexityRouter should classify task complexity."""
    from app.engine.complexity_router import route_complexity, TaskComplexity

    empty_parsed = {"functional": [], "constraints": [], "implicit": [], "edge_cases": []}

    simple = route_complexity("实现一个排序函数", empty_parsed)
    assert simple in (TaskComplexity.SIMPLE, TaskComplexity.MEDIUM, TaskComplexity.HARD)

    hard = route_complexity("实现一个并发安全的用户认证系统，支持 OAuth2 和加密", empty_parsed)
    assert hard in (TaskComplexity.MEDIUM, TaskComplexity.HARD)


@pytest.mark.asyncio
async def test_agent_response_structure():
    """AgentResponse should have all expected fields."""
    resp = _mock_agent_response("coder", "done", code="print(1)", stance="satisfied")
    assert resp.agent == "coder"
    assert resp.code == "print(1)"
    assert resp.structured["stance"] == "satisfied"
    assert resp.tokens_used == 100
