"""Tests for DebateOrchestrator integration logic."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.engine.orchestrator import DebateOrchestrator
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


@pytest.fixture
def orchestrator():
    return DebateOrchestrator()


@pytest.mark.asyncio
async def test_orchestrator_creates_result(orchestrator):
    """Orchestrator should return a DebateResult with expected fields."""
    coder_resp = _mock_agent_response("coder", "code here", code="print('hi')")
    satisfied = _mock_agent_response("security", "ok", stance="satisfied")
    judge_resp = {
        "confidence": 0.9,
        "total_issues_raised": 0,
        "accepted_and_fixed": 0,
        "rejected_by_coder": 0,
        "key_improvements": [],
        "risk_security": "low",
        "risk_performance": "low",
        "risk_correctness": "low",
    }

    with patch("app.engine.requirement_parser.call_agent") as mock_parse, \
         patch.object(orchestrator.coder, "speak", return_value=coder_resp), \
         patch("app.engine.orchestrator.ATTACKER_REGISTRY", {
             "security": MagicMock(speak=AsyncMock(return_value=satisfied)),
         }), \
         patch.object(orchestrator.judge, "summarize", return_value=judge_resp), \
         patch.object(orchestrator.test_runner, "verify") as mock_verify:

        mock_parse.return_value = AgentResponse(
            agent="requirement_parser", content="",
            structured={"functional": [], "constraints": [], "implicit": [], "edge_cases": []},
        )
        mock_verify.return_value = MagicMock(passed=True, stderr="")

        config = DebateConfig(
            max_rounds=1,
            attackers=["security"],
            skip_cross_review=True,
        )

        result = await orchestrator.run(
            requirement="test task",
            language="python",
            config=config,
        )

        assert result.code == "print('hi')"
        assert result.language == "python"
        assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_complexity_router_applied(orchestrator):
    """ComplexityRouter should adjust config for simple tasks."""
    with patch("app.engine.orchestrator.route_complexity") as mock_route, \
         patch("app.engine.orchestrator.get_debate_config") as mock_config, \
         patch("app.engine.requirement_parser.call_agent") as mock_parse, \
         patch.object(orchestrator.coder, "speak") as mock_coder, \
         patch.object(orchestrator.judge, "summarize", return_value={}), \
         patch.object(orchestrator.test_runner, "verify") as mock_verify:

        from app.engine.complexity_router import TaskComplexity
        mock_route.return_value = TaskComplexity.SIMPLE
        mock_config.return_value = {
            "max_rounds": 1,
            "attackers": [],
            "skip_cross_review": True,
        }
        mock_parse.return_value = AgentResponse(
            agent="requirement_parser", content="",
            structured={"functional": [], "constraints": [], "implicit": [], "edge_cases": []},
        )
        mock_coder.return_value = _mock_agent_response("coder", "done", code="x=1")
        mock_verify.return_value = MagicMock(passed=True, stderr="")

        result = await orchestrator.run(
            requirement="实现排序函数",
            language="python",
        )

        mock_route.assert_called_once()
        assert result.metrics.total_rounds <= 1
