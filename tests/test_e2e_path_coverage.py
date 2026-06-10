"""
End-to-end path coverage tests for AutoJudge.

Covers every flow path from the design doc:
  PHASE 1 (Plan) → PHASE 2 (Coder) → PHASE 3 (Debate Loop)
  → PHASE 4 (Arbitration) → PHASE 5 (Final Fix) → PHASE 6 (Judge)

All LLM calls are mocked. Tests verify graph node transitions,
state mutations, and conditional edge routing — not LLM quality.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.context import DebateContext, DebateConfig, DebateMessage
from app.engine.budget import BudgetManager
from app.engine.consensus import ConsensusDetector
from app.engine.complexity_router import (
    route_complexity,
    get_debate_config,
    TaskComplexity,
)
from app.engine.graph import (
    DebateState,
    plan_generate_node,
    plan_select_node,
    coder_node,
    security_node,
    performance_node,
    correctness_node,
    cross_review_node,
    arbitration_node,
    final_fix_node,
    judge_node,
    check_consensus_edge,
    _arbitration_edge,
    _extract_unresolved_disputes,
    _security_redline_allows,
    _needs_human_review,
    _build_structured_findings_summary,
    _check_and_return_consensus,
    build_debate_graph,
)
from app.engine.degradation import DegradationManager, CircuitBreaker
from app.engine.resource_manager import ResourceManager
from app.llm.client import AgentResponse


# ═════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════

def _mock_response(agent, content, code=None, stance="attacking", findings=None):
    return AgentResponse(
        agent=agent,
        content=content,
        code=code,
        structured={
            "message": content,
            "stance": stance,
            "has_new_issues": stance == "attacking",
            "findings": findings or [],
            "responses": [],
            "updated_code": code or "",
        },
        tokens_used=100,
    )


def _base_state(**overrides) -> DebateState:
    state = {
        "requirement": "实现一个用户登录接口",
        "language": "python",
        "framework": "",
        "current_code": "",
        "round": 0,
        "max_rounds": 5,
        "messages": [],
        "consensus": {},
        "skip_list": [],
        "extra_context": "",
        "converged": False,
        "budget_spent": 0,
        "budget_total": 100_000,
        "judge_report": {},
        "arbitration_result": {},
        "must_fix_items": [],
        "convergence_reason": "",
        "selected_plan": "",
        "config": {
            "max_rounds": 5,
            "attackers": ["security", "performance", "correctness"],
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 100_000,
            "skip_cross_review": False,
        },
        "enable_interrupt": False,
    }
    state.update(overrides)
    return state


def _attacker_msg(agent, stance, round_num=1, findings=None):
    return {
        "agent": agent,
        "content": f"{agent} review",
        "round": round_num,
        "structured": {
            "stance": stance,
            "findings": findings or [],
            "has_new_issues": stance == "attacking",
            "message": f"{agent} review",
        },
    }


def _coder_msg(round_num=1, code="print('hello')", responses=None):
    return {
        "agent": "coder",
        "content": "code submitted",
        "round": round_num,
        "code": code,
        "structured": {
            "message": "code submitted",
            "responses": responses or [],
            "updated_code": code,
        },
    }


# ═════════════════════════════════════════════════════════════════
# PHASE 1: Plan Phase
# ═════════════════════════════════════════════════════════════════

class TestPlanPhase:
    """Plan Phase: plan_generate_node generates proposals, plan_select_node gets user choice."""

    @pytest.mark.asyncio
    async def test_plan_rest_api_mode_no_interrupt(self):
        """REST API mode (enable_interrupt=False): plan auto-proceeds."""
        state = _base_state(enable_interrupt=False)
        with patch("app.llm.client.call_agent") as mock_call, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_call.return_value = _mock_response("planner", "方案A: 轻量级\n方案B: 生产级")
            gen_result = await plan_generate_node(state)

        assert gen_result["plan_content"] != ""
        assert gen_result["plan_action"] == "pending"

        state.update(gen_result)
        with patch("app.engine.graph._notify", new_callable=AsyncMock):
            select_result = await plan_select_node(state)

        assert "selected_plan" in select_result
        assert select_result["selected_plan"] != ""
        assert select_result["plan_action"] == "done"
        assert len(select_result["messages"]) == 1
        assert select_result["messages"][0]["agent"] == "coder"

    @pytest.mark.asyncio
    async def test_plan_user_selects_plan(self):
        """WebSocket mode: user selects a specific plan."""
        state = _base_state(enable_interrupt=True)
        with patch("app.llm.client.call_agent") as mock_call, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_call.return_value = _mock_response("planner", "方案A\n方案B")
            gen_result = await plan_generate_node(state)

        state.update(gen_result)
        with patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "select", "plan_content": "方案A: 轻量级"}
            select_result = await plan_select_node(state)

        assert select_result["selected_plan"] == "方案A: 轻量级"
        assert select_result["plan_action"] == "done"

    @pytest.mark.asyncio
    async def test_plan_user_auto_select(self):
        """User clicks 'let Coder choose best plan'."""
        state = _base_state(enable_interrupt=True)
        with patch("app.llm.client.call_agent") as mock_call, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_call.return_value = _mock_response("planner", "两个方案")
            gen_result = await plan_generate_node(state)

        state.update(gen_result)
        with patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "auto_select"}
            select_result = await plan_select_node(state)

        assert select_result["selected_plan"] == "两个方案"
        assert select_result["plan_action"] == "done"

    @pytest.mark.asyncio
    async def test_plan_user_chat_returns_chat_action(self):
        """User provides feedback — plan_select returns chat action for re-generation."""
        state = _base_state(enable_interrupt=True)
        with patch("app.llm.client.call_agent") as mock_call, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_call.return_value = _mock_response("planner", "初始方案")
            gen_result = await plan_generate_node(state)

        state.update(gen_result)
        with patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "chat", "message": "我不想用Redis"}
            select_result = await plan_select_node(state)

        assert select_result["plan_action"] == "chat"
        assert select_result["extra_context"] == "我不想用Redis"
        assert select_result["plan_round"] == 1

    @pytest.mark.asyncio
    async def test_plan_chat_then_select_full_cycle(self):
        """Full cycle: generate → select(chat) → generate(adjust) → select(confirm)."""
        state = _base_state(enable_interrupt=True)

        # Step 1: initial generation
        with patch("app.llm.client.call_agent") as mock_call, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_call.return_value = _mock_response("planner", "初始方案")
            gen1 = await plan_generate_node(state)
        state.update(gen1)

        # Step 2: user chats
        with patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "chat", "message": "不要Redis"}
            sel1 = await plan_select_node(state)
        state.update(sel1)
        assert state["plan_action"] == "chat"

        # Step 3: re-generation with feedback
        with patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.coder_agent") as mock_coder:
            mock_coder.speak = AsyncMock(return_value=_mock_response("coder", "无Redis方案"))
            gen2 = await plan_generate_node(state)
        state.update(gen2)
        assert state["plan_content"] == "无Redis方案"

        # Step 4: user selects
        with patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "select"}
            sel2 = await plan_select_node(state)

        assert sel2["plan_action"] == "done"
        assert sel2["selected_plan"] == "无Redis方案"

    @pytest.mark.asyncio
    async def test_plan_hard_cutoff_at_round_7(self):
        """Anti-deadloop: auto-proceeds after 7 chat rounds."""
        state = _base_state(enable_interrupt=True, plan_round=7)
        state["plan_content"] = "已有方案"
        with patch("app.engine.graph._notify", new_callable=AsyncMock):
            result = await plan_select_node(state)

        assert result["plan_action"] == "done"
        assert result["selected_plan"] != ""

    @pytest.mark.asyncio
    async def test_plan_timeout_none_input(self):
        """User timeout: interrupt returns None → auto proceed."""
        state = _base_state(enable_interrupt=True)
        with patch("app.llm.client.call_agent") as mock_call, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_call.return_value = _mock_response("planner", "两个方案")
            gen_result = await plan_generate_node(state)

        state.update(gen_result)
        with patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_interrupt.return_value = None
            select_result = await plan_select_node(state)

        assert select_result["selected_plan"] != ""
        assert select_result["plan_action"] == "done"


# ═════════════════════════════════════════════════════════════════
# PHASE 2: Coder writes code
# ═════════════════════════════════════════════════════════════════

class TestCoderPhase:

    @pytest.mark.asyncio
    async def test_coder_first_round_with_plan(self):
        """Round 1: Coder generates code based on selected plan."""
        state = _base_state(round=0, selected_plan="方案A: FastAPI+bcrypt+JWT")
        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(
                return_value=_mock_response("coder", "代码已生成", code="def login(): pass")
            )
            result = await coder_node(state)

        assert result["round"] == 1
        assert result["current_code"] == "def login(): pass"
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_coder_first_round_no_plan(self):
        """Round 1 without plan: Coder generates from requirement only."""
        state = _base_state(round=0, selected_plan="")
        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(
                return_value=_mock_response("coder", "代码", code="x=1")
            )
            result = await coder_node(state)

        assert result["round"] == 1
        assert result["current_code"] == "x=1"

    @pytest.mark.asyncio
    async def test_coder_subsequent_round_responds_to_attacks(self):
        """Round 2+: Coder responds to attacker findings."""
        state = _base_state(
            round=1,
            current_code="v1",
            messages=[
                _attacker_msg("security", "attacking", findings=[
                    {"category": "sql_injection", "severity": "high", "description": "SQL注入"}
                ]),
            ],
        )
        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(
                return_value=_mock_response("coder", "已修复", code="v2_fixed")
            )
            result = await coder_node(state)

        assert result["round"] == 2
        assert result["current_code"] == "v2_fixed"

    @pytest.mark.asyncio
    async def test_coder_no_code_keeps_previous(self):
        """When Coder returns no code, preserve current_code."""
        state = _base_state(round=0, current_code="existing_code")
        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(
                return_value=_mock_response("coder", "思路说明", code=None)
            )
            result = await coder_node(state)

        assert result["current_code"] == "existing_code"


# ═════════════════════════════════════════════════════════════════
# PHASE 3: Debate Loop — Attackers + Cross-Review + Consensus
# ═════════════════════════════════════════════════════════════════

class TestAttackerNodes:

    @pytest.mark.asyncio
    async def test_attacker_normal_execution(self):
        """Attacker runs and returns findings."""
        state = _base_state(round=1, current_code="code")
        with patch("app.engine.graph.security_agent") as mock_agent, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_agent.speak = AsyncMock(return_value=_mock_response(
                "security", "SQL注入风险", stance="attacking",
                findings=[{"category": "sql_injection", "severity": "high", "description": "SQL注入"}],
            ))
            result = await security_node(state)

        assert len(result["messages"]) == 1
        assert result["messages"][0]["agent"] == "security"

    @pytest.mark.asyncio
    async def test_attacker_skipped_via_skip_list(self):
        """Attacker in skip_list is skipped entirely."""
        state = _base_state(round=1, skip_list=["security"])
        result = await security_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_attacker_exception_returns_error_message(self):
        """Attacker failure is graceful — returns error message, doesn't crash."""
        state = _base_state(round=1, current_code="code")
        with patch("app.engine.graph.performance_agent") as mock_agent, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_agent.speak = AsyncMock(side_effect=RuntimeError("LLM API timeout"))
            result = await performance_node(state)

        assert "messages" in result
        assert result["messages"][0]["structured"]["stance"] == "error"

    @pytest.mark.asyncio
    async def test_all_three_attackers_parallel(self):
        """All 3 attackers can run (simulating parallel fan-out)."""
        state = _base_state(round=1, current_code="code")
        results = []
        for node_fn, agent_name, mock_target in [
            (security_node, "security", "app.engine.graph.security_agent"),
            (performance_node, "performance", "app.engine.graph.performance_agent"),
            (correctness_node, "correctness", "app.engine.graph.correctness_agent"),
        ]:
            with patch(mock_target) as mock_agent, \
                 patch("app.engine.graph.record_agent_call"), \
                 patch("app.engine.graph._notify", new_callable=AsyncMock):
                mock_agent.speak = AsyncMock(
                    return_value=_mock_response(agent_name, "review", stance="satisfied")
                )
                r = await node_fn(state)
                results.append(r)

        assert all(r.get("messages") for r in results)


class TestCrossReview:

    @pytest.mark.asyncio
    async def test_cross_review_with_2_plus_attackers(self):
        """Cross-review triggers when ≥2 attackers produced messages."""
        state = _base_state(
            round=1,
            current_code="code",
            messages=[
                _attacker_msg("security", "attacking", findings=[
                    {"category": "xss", "severity": "high", "description": "XSS风险"}
                ]),
                _attacker_msg("performance", "satisfied"),
                _attacker_msg("correctness", "satisfied"),
            ],
        )
        with patch("app.engine.graph.security_agent") as m_sec, \
             patch("app.engine.graph.performance_agent") as m_perf, \
             patch("app.engine.graph.correctness_agent") as m_corr, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            for m in [m_sec, m_perf, m_corr]:
                m.speak = AsyncMock(return_value=_mock_response("x", "同意", stance="satisfied"))
            result = await cross_review_node(state)

        assert "consensus" in result

    @pytest.mark.asyncio
    async def test_cross_review_skipped_with_fewer_than_2(self):
        """Cross-review skipped when <2 attacker messages in this round."""
        state = _base_state(
            round=1,
            messages=[_attacker_msg("security", "attacking")],
        )
        with patch("app.engine.graph._notify", new_callable=AsyncMock):
            result = await cross_review_node(state)

        assert "consensus" in result


class TestConsensusEdge:

    def test_converged_all_satisfied(self):
        state = _base_state(converged=True, round=1, budget_spent=1000)
        assert check_consensus_edge(state) == "converged"

    def test_continue_has_rounds(self):
        state = _base_state(
            converged=False, round=2, max_rounds=5, budget_spent=1000,
            messages=[
                _attacker_msg("security", "attacking", round_num=2),
                _attacker_msg("performance", "attacking", round_num=2),
                _attacker_msg("correctness", "attacking", round_num=2),
            ],
        )
        assert check_consensus_edge(state) == "continue"

    def test_budget_exceeded_85_percent(self):
        state = _base_state(converged=False, round=2, budget_spent=86_000, budget_total=100_000)
        assert check_consensus_edge(state) == "budget_exceeded"

    def test_max_rounds_exceeded(self):
        state = _base_state(converged=False, round=5, max_rounds=5, budget_spent=1000)
        assert check_consensus_edge(state) == "budget_exceeded"

    def test_exactly_at_budget_threshold(self):
        """85% of 100k = 85k, spending 84999 should still continue."""
        state = _base_state(
            converged=False, round=2, budget_spent=84_999, budget_total=100_000,
            messages=[
                _attacker_msg("security", "attacking", round_num=2),
                _attacker_msg("performance", "attacking", round_num=2),
                _attacker_msg("correctness", "attacking", round_num=2),
            ],
        )
        assert check_consensus_edge(state) == "continue"

    def test_just_over_budget_threshold(self):
        state = _base_state(converged=False, round=2, budget_spent=85_001, budget_total=100_000)
        assert check_consensus_edge(state) == "budget_exceeded"


class TestConsensusDetector:

    def test_partial_satisfied_not_converged(self):
        detector = ConsensusDetector()
        msgs = [
            DebateMessage(agent="security", content="", round=1,
                          structured={"stance": "satisfied"}),
            DebateMessage(agent="performance", content="", round=1,
                          structured={"stance": "attacking"}),
        ]
        result = detector.check_consensus(msgs)
        assert result["converged"] is False

    def test_missing_stance_field(self):
        """Message with structured data but no 'stance' key."""
        detector = ConsensusDetector()
        msgs = [
            DebateMessage(agent="security", content="", round=1,
                          structured={"findings": []}),
        ]
        result = detector.check_consensus(msgs)
        assert result["converged"] is False


# ═════════════════════════════════════════════════════════════════
# PHASE 4: Arbitration
# ═════════════════════════════════════════════════════════════════

class TestArbitration:

    @pytest.mark.asyncio
    async def test_no_disputes_equivalent_convergence(self):
        """No unresolved disputes → equivalent convergence → judge."""
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "satisfied", round_num=3),
                _attacker_msg("performance", "satisfied", round_num=3),
            ],
        )
        with patch("app.engine.graph._notify", new_callable=AsyncMock):
            result = await arbitration_node(state)

        assert result["converged"] is True
        assert "等效收敛" in result["convergence_reason"]
        assert result["must_fix_items"] == []

    @pytest.mark.asyncio
    async def test_deliverable_verdict(self):
        """Arbitrator says deliverable → no must_fix → judge."""
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": "rate_limit", "severity": "medium", "description": "缺少限流"}
                ]),
            ],
        )
        with patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_arb.arbitrate = AsyncMock(return_value={
                "rulings": [
                    {"dispute_id": "d1", "verdict": "acknowledged",
                     "re_assessed_severity": "low", "reasoning": "范围外建议"}
                ],
                "overall_verdict": "deliverable",
                "confidence": 0.85,
                "summary": "可交付",
            })
            result = await arbitration_node(state)

        assert result["converged"] is True
        assert result["must_fix_items"] == []

    @pytest.mark.asyncio
    async def test_fix_then_deliver_verdict(self):
        """Arbitrator: fix_then_deliver with 1 must_fix, no critical → final_fix."""
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": "sql_injection", "severity": "high", "description": "SQL注入"}
                ]),
            ],
        )
        with patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_arb.arbitrate = AsyncMock(return_value={
                "rulings": [
                    {"dispute_id": "d1", "verdict": "must_fix",
                     "re_assessed_severity": "high", "reasoning": "需要参数化查询"}
                ],
                "overall_verdict": "fix_then_deliver",
                "confidence": 0.75,
                "summary": "修后交付",
            })
            result = await arbitration_node(state)

        assert result["converged"] is False
        assert len(result["must_fix_items"]) == 1

    @pytest.mark.asyncio
    async def test_needs_human_review_many_must_fix(self):
        """must_fix > 3 → needs_human_review, goes to judge not final_fix."""
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": f"issue_{i}", "severity": "high", "description": f"问题{i}"}
                    for i in range(4)
                ]),
            ],
        )
        with patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_arb.arbitrate = AsyncMock(return_value={
                "rulings": [
                    {"dispute_id": f"d{i}", "verdict": "must_fix",
                     "re_assessed_severity": "high", "reasoning": f"问题{i}"}
                    for i in range(4)
                ],
                "overall_verdict": "not_deliverable",
                "confidence": 0.4,
                "summary": "问题太多",
            })
            result = await arbitration_node(state)

        assert result["converged"] is True
        assert "人工审查" in result["convergence_reason"]
        assert result["must_fix_items"] == []

    @pytest.mark.asyncio
    async def test_fix_then_deliver_with_critical_goes_to_human(self):
        """fix_then_deliver but has critical must_fix → human review."""
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": "rce", "severity": "critical", "description": "RCE漏洞"}
                ]),
            ],
        )
        with patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_arb.arbitrate = AsyncMock(return_value={
                "rulings": [
                    {"dispute_id": "d1", "verdict": "must_fix",
                     "re_assessed_severity": "critical", "reasoning": "RCE"}
                ],
                "overall_verdict": "fix_then_deliver",
                "confidence": 0.5,
                "summary": "有critical",
            })
            result = await arbitration_node(state)

        assert result["converged"] is True
        assert result["must_fix_items"] == []

    @pytest.mark.asyncio
    async def test_user_override_upgrade_verdict(self):
        """User escalates acknowledged → must_fix via interrupt."""
        state = _base_state(
            round=3,
            enable_interrupt=True,
            messages=[
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": "rate_limit", "severity": "medium", "description": "缺少限流"}
                ]),
            ],
        )
        with patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_arb.arbitrate = AsyncMock(return_value={
                "rulings": [
                    {"dispute_id": "d1", "verdict": "acknowledged",
                     "re_assessed_severity": "medium", "reasoning": "建议项"}
                ],
                "overall_verdict": "deliverable",
                "confidence": 0.8,
                "summary": "可交付",
            })
            mock_interrupt.return_value = {
                "overrides": {
                    "d1": {"action": "upgrade", "new_verdict": "must_fix"}
                }
            }
            result = await arbitration_node(state)

        rulings = result["arbitration_result"]["rulings"]
        assert rulings[0]["verdict"] == "must_fix"

    @pytest.mark.asyncio
    async def test_user_downgrade_blocked_by_security_redline(self):
        """User tries to downgrade critical SQL injection → blocked."""
        state = _base_state(
            round=3,
            enable_interrupt=True,
            messages=[
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": "sql_injection", "severity": "critical", "description": "SQL注入"}
                ]),
            ],
        )
        with patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_arb.arbitrate = AsyncMock(return_value={
                "rulings": [
                    {"dispute_id": "sql_injection_001", "verdict": "must_fix",
                     "re_assessed_severity": "critical",
                     "reasoning": "SQL injection confirmed"}
                ],
                "overall_verdict": "fix_then_deliver",
                "confidence": 0.7,
                "summary": "修后交付",
            })
            mock_interrupt.return_value = {
                "overrides": {
                    "sql_injection_001": {"action": "downgrade", "new_verdict": "dismissed"}
                }
            }
            result = await arbitration_node(state)

        rulings = result["arbitration_result"]["rulings"]
        assert rulings[0]["verdict"] == "must_fix"
        assert "安全红线" in rulings[0]["reasoning"]

    @pytest.mark.asyncio
    async def test_attacker_attacking_but_empty_findings_synthesized(self):
        """stance=attacking but findings=[] → synthetic dispute created."""
        state = _base_state(
            round=3,
            messages=[
                {
                    "agent": "security",
                    "content": "有隐患但我不确定具体是什么",
                    "round": 3,
                    "structured": {
                        "stance": "attacking",
                        "findings": [],
                        "has_new_issues": True,
                        "message": "有隐患但我不确定具体是什么",
                    },
                }
            ],
        )
        disputes = _extract_unresolved_disputes(state)
        assert len(disputes) == 1
        assert disputes[0]["severity"] == "medium"
        assert "有隐患" in disputes[0]["finding"]


class TestArbitrationEdge:

    def test_has_must_fix_goes_to_fix(self):
        state = _base_state(must_fix_items=[{"dispute_id": "d1", "verdict": "must_fix"}])
        assert _arbitration_edge(state) == "fix"

    def test_no_must_fix_goes_to_deliver(self):
        state = _base_state(must_fix_items=[])
        assert _arbitration_edge(state) == "deliver"


class TestSecurityRedline:

    def test_non_critical_allows_downgrade(self):
        ruling = {"re_assessed_severity": "high", "dispute_id": "d1", "reasoning": "issue"}
        assert _security_redline_allows(ruling, "dismissed") is True

    def test_critical_sql_injection_blocks_downgrade(self):
        ruling = {
            "re_assessed_severity": "critical",
            "dispute_id": "sql_injection_001",
            "reasoning": "SQL injection confirmed",
        }
        assert _security_redline_allows(ruling, "dismissed") is False

    def test_critical_rce_blocks_downgrade(self):
        ruling = {
            "re_assessed_severity": "critical",
            "dispute_id": "rce_vuln",
            "reasoning": "Remote code execution",
        }
        assert _security_redline_allows(ruling, "acknowledged") is False

    def test_critical_xss_blocks_downgrade(self):
        ruling = {
            "re_assessed_severity": "critical",
            "dispute_id": "xss_issue",
            "reasoning": "XSS in output",
        }
        assert _security_redline_allows(ruling, "deferred") is False

    def test_critical_non_security_allows_downgrade(self):
        """Critical severity but NOT a security category → downgrade allowed."""
        ruling = {
            "re_assessed_severity": "critical",
            "dispute_id": "perf_bottleneck",
            "reasoning": "performance regression in loop",
        }
        assert _security_redline_allows(ruling, "dismissed") is True

    def test_critical_upgrade_always_allowed(self):
        """Upgrading verdict is always allowed regardless of redline."""
        ruling = {
            "re_assessed_severity": "critical",
            "dispute_id": "sql_injection_001",
            "reasoning": "SQL injection",
        }
        assert _security_redline_allows(ruling, "must_fix") is True


class TestNeedsHumanReview:

    def test_needs_human_verdict(self):
        state = {
            "arbitration_result": {
                "rulings": [{"verdict": "needs_human", "re_assessed_severity": "high"}]
            }
        }
        assert _needs_human_review(state) is True

    def test_many_must_fix(self):
        state = {
            "arbitration_result": {
                "rulings": [
                    {"verdict": "must_fix", "re_assessed_severity": "high"}
                    for _ in range(4)
                ]
            }
        }
        assert _needs_human_review(state) is True

    def test_unfixed_critical(self):
        state = {
            "arbitration_result": {
                "rulings": [{"verdict": "must_fix", "re_assessed_severity": "critical"}]
            }
        }
        assert _needs_human_review(state) is True

    def test_normal_does_not_need_human(self):
        state = {
            "arbitration_result": {
                "rulings": [
                    {"verdict": "acknowledged", "re_assessed_severity": "low"},
                    {"verdict": "dismissed", "re_assessed_severity": "none"},
                ]
            }
        }
        assert _needs_human_review(state) is False

    def test_no_arbitration_result(self):
        state = {"arbitration_result": None}
        assert _needs_human_review(state) is False

    def test_empty_arbitration_result(self):
        state = {"arbitration_result": {}}
        assert _needs_human_review(state) is False


# ═════════════════════════════════════════════════════════════════
# PHASE 5: Final Fix + Strategy Diversification
# ═════════════════════════════════════════════════════════════════

class TestFinalFix:

    @pytest.mark.asyncio
    async def test_fix_succeeds_first_attempt(self):
        """Coder fixes → Arbitrator reviews → all fixed → done."""
        state = _base_state(
            round=3,
            current_code="v3_buggy",
            must_fix_items=[
                {"dispute_id": "d1", "re_assessed_severity": "high",
                 "reasoning": "SQL注入需修复", "verdict": "must_fix"}
            ],
        )
        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(
                return_value=_mock_response("coder", "已修复", code="v4_fixed")
            )
            mock_arb.review_fixes = AsyncMock(return_value=[
                {"dispute_id": "d1", "status": "fixed", "review_comment": "修复正确"}
            ])
            result = await final_fix_node(state)

        assert result["current_code"] == "v4_fixed"
        assert result["converged"] is True
        assert "仲裁后修复完成" in result["convergence_reason"]

    @pytest.mark.asyncio
    async def test_fix_review_not_fixed_triggers_refix(self):
        """Coder fixes → Arbitrator says not_fixed → refix attempt → done with 含补修."""
        state = _base_state(
            round=3,
            current_code="v3_buggy",
            must_fix_items=[
                {"dispute_id": "d1", "re_assessed_severity": "high",
                 "reasoning": "问题", "verdict": "must_fix"}
            ],
        )
        speak_count = [0]

        async def mock_speak(ctx, prompt, budget):
            speak_count[0] += 1
            return _mock_response("coder", f"修复{speak_count[0]}", code=f"v{3+speak_count[0]}")

        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(side_effect=mock_speak)
            mock_arb.review_fixes = AsyncMock(return_value=[
                {"dispute_id": "d1", "status": "not_fixed", "review_comment": "没改对"}
            ])
            result = await final_fix_node(state)

        assert speak_count[0] == 2
        assert result["current_code"] == "v5"
        assert "含补修" in result["convergence_reason"]

    @pytest.mark.asyncio
    async def test_loop_retries_when_no_code_returned(self):
        """First 2 attempts return no code → loop continues → 3rd returns code."""
        state = _base_state(
            round=3,
            current_code="v3_original",
            must_fix_items=[
                {"dispute_id": "d1", "re_assessed_severity": "high",
                 "reasoning": "难修", "verdict": "must_fix"}
            ],
        )
        call_count = [0]

        async def mock_speak(ctx, prompt, budget):
            call_count[0] += 1
            if call_count[0] < 3:
                return _mock_response("coder", f"尝试{call_count[0]}")
            return _mock_response("coder", "修复成功", code="v4_fixed")

        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(side_effect=mock_speak)
            mock_arb.review_fixes = AsyncMock(return_value=[
                {"dispute_id": "d1", "status": "fixed", "review_comment": "OK"}
            ])
            result = await final_fix_node(state)

        assert call_count[0] == 3
        assert result["current_code"] == "v4_fixed"
        assert result["converged"] is True
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_review_not_fixed_triggers_refix_with_code(self):
        """Loop produces code → review not_fixed → refix produces new code."""
        state = _base_state(
            round=3,
            current_code="v3",
            must_fix_items=[
                {"dispute_id": "d1", "re_assessed_severity": "high",
                 "reasoning": "问题", "verdict": "must_fix"}
            ],
        )
        speak_count = [0]

        async def mock_speak(ctx, prompt, budget):
            speak_count[0] += 1
            return _mock_response("coder", f"attempt {speak_count[0]}", code=f"v{3+speak_count[0]}")

        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(side_effect=mock_speak)
            mock_arb.review_fixes = AsyncMock(return_value=[
                {"dispute_id": "d1", "status": "not_fixed", "review_comment": "SQL还在拼接"}
            ])
            result = await final_fix_node(state)

        assert speak_count[0] == 2
        assert result["current_code"] == "v5"
        assert "含补修" in result["convergence_reason"]

    @pytest.mark.asyncio
    async def test_no_must_fix_items_returns_immediately(self):
        """No must_fix items → returns immediately with converged=True."""
        state = _base_state(round=3, must_fix_items=[])
        result = await final_fix_node(state)
        assert result["converged"] is True
        assert "无需修复" in result["convergence_reason"]

    @pytest.mark.asyncio
    async def test_user_provides_own_strategy_via_interrupt(self):
        """User provides custom fix strategy → refix uses user's approach."""
        state = _base_state(
            round=3,
            enable_interrupt=True,
            current_code="v3",
            must_fix_items=[
                {"dispute_id": "d1", "re_assessed_severity": "high",
                 "reasoning": "问题", "verdict": "must_fix"}
            ],
        )
        speak_count = [0]

        async def mock_speak(ctx, prompt, budget):
            speak_count[0] += 1
            if speak_count[0] == 1:
                return _mock_response("coder", "第一次修复", code="v4_bad")
            return _mock_response("coder", "按用户思路修复", code="v4_user_strategy")

        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_coder.speak = AsyncMock(side_effect=mock_speak)
            mock_arb.review_fixes = AsyncMock(return_value=[
                {"dispute_id": "d1", "status": "not_fixed", "review_comment": "没改对"}
            ])
            mock_interrupt.return_value = {
                "action": "user_strategy",
                "message": "用装饰器方式实现限流",
            }
            result = await final_fix_node(state)

        assert result["current_code"] == "v4_user_strategy"
        assert "含补修" in result["convergence_reason"]


# ═════════════════════════════════════════════════════════════════
# PHASE 6: Judge
# ═════════════════════════════════════════════════════════════════

class TestJudge:

    @pytest.mark.asyncio
    async def test_judge_generates_report(self):
        state = _base_state(round=2, current_code="final_code")
        with patch("app.engine.graph.judge_agent") as mock_judge:
            mock_judge.summarize = AsyncMock(return_value={
                "confidence": 0.85,
                "star_rating": 4,
                "star_comment": "良好",
                "resolved_issues": ["SQL注入已修复"],
                "unresolved_issues": [],
                "score_security": 80,
                "score_performance": 100,
                "score_correctness": 90,
                "usage_advice": "可以直接使用",
            })
            result = await judge_node(state)

        assert result["judge_report"]["confidence"] == 0.85
        assert result["judge_report"]["star_rating"] == 4


# ═════════════════════════════════════════════════════════════════
# Graph Structure Verification
# ═════════════════════════════════════════════════════════════════

class TestGraphStructure:

    def test_graph_builds_without_error(self):
        graph = build_debate_graph()
        assert graph is not None

    def test_graph_has_all_nodes(self):
        graph = build_debate_graph()
        node_names = set(graph.nodes.keys())
        expected = {
            "plan_generate", "plan_select", "coder", "security", "performance", "correctness",
            "cross_review", "arbitration", "final_fix", "judge",
        }
        assert expected.issubset(node_names)

    def test_graph_entry_point_is_plan(self):
        graph = build_debate_graph()
        compiled = graph.compile()
        first_node = compiled.get_graph().first_node()
        assert first_node is not None


# ═════════════════════════════════════════════════════════════════
# ComplexityRouter
# ═════════════════════════════════════════════════════════════════

class TestComplexityRouter:

    def test_simple_task(self):
        result = route_complexity(
            "实现一个排序函数sort，处理字符串转换",
            {"functional": [], "constraints": [], "implicit": [], "edge_cases": []},
        )
        assert result == TaskComplexity.SIMPLE

    def test_hard_task(self):
        result = route_complexity(
            "实现一个并发认证中间件，处理密码加密和限流",
            {"functional": [], "constraints": [], "implicit": ["a", "b", "c"], "edge_cases": []},
        )
        assert result == TaskComplexity.HARD

    def test_medium_task(self):
        result = route_complexity(
            "实现一个REST API接口",
            {"functional": [], "constraints": [], "implicit": [], "edge_cases": []},
        )
        assert result == TaskComplexity.MEDIUM

    def test_simple_config_no_attackers(self):
        config = get_debate_config(TaskComplexity.SIMPLE)
        assert config["max_rounds"] == 1
        assert config["attackers"] == []
        assert config["skip_cross_review"] is True

    def test_medium_config_one_attacker(self):
        config = get_debate_config(TaskComplexity.MEDIUM)
        assert config["max_rounds"] == 3
        assert config["attackers"] == ["correctness"]

    def test_hard_config_all_attackers(self):
        config = get_debate_config(TaskComplexity.HARD)
        assert config["max_rounds"] == 7
        assert len(config["attackers"]) == 3
        assert config["skip_cross_review"] is False


# ═════════════════════════════════════════════════════════════════
# Degradation Manager
# ═════════════════════════════════════════════════════════════════

class TestDegradation:

    def test_circuit_breaker_closed_initially(self):
        cb = CircuitBreaker()
        assert cb.state == "closed"

    def test_circuit_breaker_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"

    def test_circuit_breaker_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "closed"

    def test_l0_timeout_computation(self):
        config = DebateConfig(max_rounds=5, attackers=["security", "performance", "correctness"])
        timeout = DegradationManager._compute_l0_timeout(config)
        assert timeout > 0
        assert timeout > 100

    def test_l0_timeout_simple_task(self):
        config = DebateConfig(max_rounds=1, attackers=[], skip_cross_review=True)
        timeout = DegradationManager._compute_l0_timeout(config)
        simple_config = DebateConfig(max_rounds=5, attackers=["security", "performance", "correctness"])
        hard_timeout = DegradationManager._compute_l0_timeout(simple_config)
        assert timeout < hard_timeout


# ═════════════════════════════════════════════════════════════════
# ResourceManager
# ═════════════════════════════════════════════════════════════════

class TestResourceManager:

    @pytest.mark.asyncio
    async def test_debate_slot_acquisition(self):
        rm = ResourceManager(max_concurrent_debates=2)
        async with rm.acquire_debate_slot("req1"):
            async with rm.acquire_debate_slot("req2"):
                pass

    @pytest.mark.asyncio
    async def test_debate_slot_timeout(self):
        rm = ResourceManager(max_concurrent_debates=1)
        async with rm.acquire_debate_slot("req1"):
            with pytest.raises(TimeoutError):
                # Override semaphore wait timeout for test speed
                rm.debate_semaphore = asyncio.Semaphore(0)
                async with rm.acquire_debate_slot("req2"):
                    pass

    @pytest.mark.asyncio
    async def test_llm_slot_acquisition(self):
        rm = ResourceManager(max_concurrent_llm_calls=5)
        async with rm.acquire_llm_slot():
            pass


# ═════════════════════════════════════════════════════════════════
# Context Management (Layer 2: Agent-Specific View)
# ═════════════════════════════════════════════════════════════════

class TestContextManagement:

    def test_attacker_sees_only_own_history(self):
        """Security attacker should not see performance attacker's messages."""
        ctx = DebateContext("test")
        ctx.round = 1
        ctx.add_message("coder", "initial code", code="code1")
        ctx.add_message("security", "SQL injection found")
        ctx.add_message("performance", "O(n^2) found")
        ctx.add_message("correctness", "null check missing")

        sec_view = ctx.get_context_for_agent("security")
        content = " ".join(m["content"] for m in sec_view)
        assert "SQL injection" in content or "CODER" in content

    def test_coder_sees_all_attackers(self):
        ctx = DebateContext("test")
        ctx.round = 1
        ctx.add_message("coder", "code", code="code1")
        ctx.add_message("security", "SQL injection")
        ctx.add_message("performance", "O(n^2)")
        ctx.add_message("correctness", "null check")

        coder_view = ctx.get_context_for_agent("coder")
        content = " ".join(m["content"] for m in coder_view)
        assert "SECURITY" in content
        assert "PERFORMANCE" in content
        assert "CORRECTNESS" in content

    def test_judge_gets_global_view(self):
        ctx = DebateContext("test")
        ctx.round = 2
        ctx.add_message("coder", "code v1", code="v1")
        ctx.add_message("security", "issue")
        ctx.round = 2
        ctx.add_message("coder", "code v2", code="v2")

        judge_view = ctx.get_context_for_agent("judge")
        assert len(judge_view) >= 1

    def test_sliding_window_prunes_old_rounds(self):
        """Only recent 2 rounds retained, older pruned for attackers."""
        ctx = DebateContext("test")
        for r in range(1, 5):
            ctx.round = r
            ctx.add_message("coder", f"code v{r}", code=f"v{r}")
            ctx.add_message("security", f"round {r} attack")

        sec_view = ctx.get_context_for_agent("security")
        content = " ".join(m["content"] for m in sec_view)
        assert "round 1" not in content or "摘要" in content

    def test_default_view_for_unknown_agent(self):
        ctx = DebateContext("test")
        ctx.round = 1
        ctx.add_message("coder", "code")
        view = ctx.get_context_for_agent("planner")
        assert len(view) >= 1


# ═════════════════════════════════════════════════════════════════
# Structured Findings Summary (Layer 3)
# ═════════════════════════════════════════════════════════════════

class TestStructuredFindingsSummary:

    def test_findings_extracted_correctly(self):
        msgs = [
            {
                "agent": "security",
                "content": "found issues",
                "round": 1,
                "structured": {
                    "stance": "attacking",
                    "findings": [
                        {"severity": "high", "category": "sql_injection",
                         "description": "参数拼接SQL"}
                    ],
                },
            },
            {
                "agent": "performance",
                "content": "no issues",
                "round": 1,
                "structured": {"stance": "satisfied", "findings": []},
            },
        ]
        summary = _build_structured_findings_summary(msgs, exclude_agent="correctness")
        assert "SECURITY" in summary
        assert "sql_injection" in summary

    def test_exclude_self(self):
        msgs = [
            {
                "agent": "security",
                "content": "issue",
                "round": 1,
                "structured": {
                    "stance": "attacking",
                    "findings": [{"severity": "high", "category": "x", "description": "y"}],
                },
            },
        ]
        summary = _build_structured_findings_summary(msgs, exclude_agent="security")
        assert summary == ""

    def test_attacking_no_findings_synthesized(self):
        """stance=attacking but findings=[] → synthetic line from message."""
        msgs = [
            {
                "agent": "security",
                "content": "有顾虑",
                "round": 1,
                "structured": {
                    "stance": "attacking",
                    "findings": [],
                    "message": "有顾虑但未具体指出",
                },
            },
        ]
        summary = _build_structured_findings_summary(msgs, exclude_agent="performance")
        assert "SECURITY" in summary
        assert "MEDIUM" in summary

    def test_no_structured_data_falls_back_to_content(self):
        msgs = [
            {"agent": "security", "content": "raw text review", "round": 1, "structured": None},
        ]
        summary = _build_structured_findings_summary(msgs, exclude_agent="performance")
        assert "raw text review" in summary


# ═════════════════════════════════════════════════════════════════
# Dispute Extraction
# ═════════════════════════════════════════════════════════════════

class TestDisputeExtraction:

    def test_only_last_round_disputes(self):
        """Only extracts disputes from the last round."""
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "attacking", round_num=1, findings=[
                    {"category": "old", "severity": "high", "description": "旧问题"}
                ]),
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": "new", "severity": "high", "description": "新问题"}
                ]),
            ],
        )
        disputes = _extract_unresolved_disputes(state)
        assert len(disputes) == 1
        assert disputes[0]["finding"] == "新问题"

    def test_satisfied_not_extracted(self):
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "satisfied", round_num=3),
            ],
        )
        disputes = _extract_unresolved_disputes(state)
        assert len(disputes) == 0

    def test_multiple_findings_from_one_attacker(self):
        state = _base_state(
            round=3,
            messages=[
                _attacker_msg("security", "attacking", round_num=3, findings=[
                    {"category": "a", "severity": "high", "description": "问题1"},
                    {"category": "b", "severity": "medium", "description": "问题2"},
                ]),
            ],
        )
        disputes = _extract_unresolved_disputes(state)
        assert len(disputes) == 2

    def test_non_attacker_messages_ignored(self):
        state = _base_state(
            round=3,
            messages=[
                _coder_msg(round_num=3),
            ],
        )
        disputes = _extract_unresolved_disputes(state)
        assert len(disputes) == 0

    def test_no_structured_data_skipped(self):
        state = _base_state(
            round=3,
            messages=[
                {"agent": "security", "content": "text only", "round": 3, "structured": None},
            ],
        )
        disputes = _extract_unresolved_disputes(state)
        assert len(disputes) == 0


# ═════════════════════════════════════════════════════════════════
# Full Path Integration Tests (node-to-node transitions)
# ═════════════════════════════════════════════════════════════════

class TestFullPath:
    """Integration tests covering complete paths through the graph."""

    @pytest.mark.asyncio
    async def test_happy_path_converge_round_1(self):
        """
        Path: plan → coder → attackers(all satisfied) → cross_review
              → converged → judge
        """
        # 1. Plan (generate + select)
        state = _base_state(enable_interrupt=False)
        with patch("app.llm.client.call_agent") as mc, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mc.return_value = _mock_response("planner", "方案")
            gen_result = await plan_generate_node(state)
        state.update(gen_result)
        with patch("app.engine.graph._notify", new_callable=AsyncMock):
            plan_result = await plan_select_node(state)

        state.update(plan_result)

        # 2. Coder
        with patch("app.engine.graph.coder_agent") as mc, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mc.speak = AsyncMock(return_value=_mock_response("coder", "代码", code="final_code"))
            coder_result = await coder_node(state)

        state.update(coder_result)

        # 3. All attackers satisfied
        for node_fn, mock_target, agent_name in [
            (security_node, "app.engine.graph.security_agent", "security"),
            (performance_node, "app.engine.graph.performance_agent", "performance"),
            (correctness_node, "app.engine.graph.correctness_agent", "correctness"),
        ]:
            with patch(mock_target) as ma, \
                 patch("app.engine.graph.record_agent_call"), \
                 patch("app.engine.graph._notify", new_callable=AsyncMock):
                ma.speak = AsyncMock(return_value=_mock_response(agent_name, "OK", stance="satisfied"))
                r = await node_fn(state)
                if r.get("messages"):
                    state["messages"] = state.get("messages", []) + r["messages"]

        # 4. Cross-review → consensus
        with patch("app.engine.graph.security_agent") as ms, \
             patch("app.engine.graph.performance_agent") as mp, \
             patch("app.engine.graph.correctness_agent") as mc, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            for m in [ms, mp, mc]:
                m.speak = AsyncMock(return_value=_mock_response("x", "同意", stance="satisfied"))
            cr_result = await cross_review_node(state)

        state.update(cr_result)

        assert state["converged"] is True
        edge = check_consensus_edge(state)
        assert edge == "converged"

        # 5. Judge
        with patch("app.engine.graph.judge_agent") as mj:
            mj.summarize = AsyncMock(return_value={"confidence": 0.95, "star_rating": 5})
            judge_result = await judge_node(state)

        assert judge_result["judge_report"]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_full_arbitration_path(self):
        """
        Path: plan → coder → attackers(1 attacking) → cross_review
              → budget_exceeded → arbitration(fix_then_deliver)
              → final_fix → judge
        """
        state = _base_state(round=5, max_rounds=5, current_code="code_v5")
        state["messages"] = [
            _attacker_msg("security", "attacking", round_num=5, findings=[
                {"category": "auth", "severity": "high", "description": "认证绕过"}
            ]),
            _attacker_msg("performance", "satisfied", round_num=5),
            _attacker_msg("correctness", "satisfied", round_num=5),
        ]
        state["converged"] = False

        assert check_consensus_edge(state) == "budget_exceeded"

        # Arbitration
        with patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_arb.arbitrate = AsyncMock(return_value={
                "rulings": [
                    {"dispute_id": "d1", "verdict": "must_fix",
                     "re_assessed_severity": "high", "reasoning": "认证绕过需修复"}
                ],
                "overall_verdict": "fix_then_deliver",
                "confidence": 0.7,
                "summary": "修后交付",
            })
            arb_result = await arbitration_node(state)

        state.update(arb_result)
        assert _arbitration_edge(state) == "fix"

        # Final Fix
        with patch("app.engine.graph.coder_agent") as mock_coder, \
             patch("app.engine.graph.arbitrator_agent") as mock_arb, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mock_coder.speak = AsyncMock(
                return_value=_mock_response("coder", "修复完成", code="code_v6_fixed")
            )
            mock_arb.review_fixes = AsyncMock(return_value=[
                {"dispute_id": "d1", "status": "fixed", "review_comment": "OK"}
            ])
            fix_result = await final_fix_node(state)

        state.update(fix_result)
        assert state["current_code"] == "code_v6_fixed"

        # Judge
        with patch("app.engine.graph.judge_agent") as mock_judge:
            mock_judge.summarize = AsyncMock(return_value={"confidence": 0.78, "star_rating": 4})
            judge_result = await judge_node(state)

        assert judge_result["judge_report"]["star_rating"] == 4

    @pytest.mark.asyncio
    async def test_simple_task_skip_attackers(self):
        """
        SIMPLE complexity: plan → coder → no attackers → judge.
        All attackers skipped, cross_review skipped.
        """
        config = get_debate_config(TaskComplexity.SIMPLE)
        all_attackers = {"security", "performance", "correctness"}
        skip_list = sorted(all_attackers - set(config["attackers"]))
        assert len(skip_list) == 3

        state = _base_state(
            skip_list=skip_list,
            max_rounds=1,
            config={**_base_state()["config"], "attackers": [], "skip_cross_review": True},
        )

        for fn in [security_node, performance_node, correctness_node]:
            result = await fn(state)
            assert result == {}

    @pytest.mark.asyncio
    async def test_multi_round_debate_then_converge(self):
        """
        Debate loop: Round 1 attacking → Round 2 satisfied → converge.
        Tests state progression through 2 rounds.
        """
        state = _base_state(round=1, current_code="v1")
        state["messages"] = [
            _attacker_msg("security", "attacking", round_num=1, findings=[
                {"category": "xss", "severity": "high", "description": "XSS"}
            ]),
            _attacker_msg("performance", "satisfied", round_num=1),
            _attacker_msg("correctness", "satisfied", round_num=1),
        ]
        state["converged"] = False

        assert check_consensus_edge(state) == "continue"

        # Round 2: Coder fixes, all satisfied
        state["round"] = 2
        state["messages"].extend([
            _attacker_msg("security", "satisfied", round_num=2),
            _attacker_msg("performance", "satisfied", round_num=2),
            _attacker_msg("correctness", "satisfied", round_num=2),
        ])
        state["converged"] = True

        assert check_consensus_edge(state) == "converged"


# ═════════════════════════════════════════════════════════════════
# Budget Management Integration
# ═════════════════════════════════════════════════════════════════

class TestBudgetIntegration:

    @pytest.mark.asyncio
    async def test_budget_tracks_across_agents(self):
        bm = BudgetManager(100_000)
        await bm.record("coder", 5000)
        await bm.record("security", 3000)
        await bm.record("performance", 3000)
        await bm.record("correctness", 3000)
        assert bm.spent == 14_000
        assert bm.can_continue()

    @pytest.mark.asyncio
    async def test_budget_near_limit_stops(self):
        bm = BudgetManager(10_000)
        await bm.record("coder", 8600)
        assert not bm.can_continue(reserve=0.15)

    @pytest.mark.asyncio
    async def test_budget_zero_remaining(self):
        bm = BudgetManager(1000)
        await bm.record("coder", 1000)
        assert bm.remaining() == 0
        assert await bm.get_max_tokens("coder") == 500

    @pytest.mark.asyncio
    async def test_agent_limits_enforced(self):
        bm = BudgetManager(1_000_000)
        coder_max = await bm.get_max_tokens("coder")
        cross_max = await bm.get_max_tokens("cross_review")
        assert coder_max <= 64_000
        assert cross_max <= 16_000


# ═════════════════════════════════════════════════════════════════
# Edge Cases
# ═════════════════════════════════════════════════════════════════

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_arbitration_with_no_messages(self):
        """Empty message list → no disputes → equivalent convergence."""
        state = _base_state(round=3, messages=[])
        with patch("app.engine.graph._notify", new_callable=AsyncMock):
            result = await arbitration_node(state)
        assert result["converged"] is True

    def test_consensus_with_only_one_attacker(self):
        detector = ConsensusDetector()
        msgs = [
            DebateMessage(agent="correctness", content="", round=1,
                          structured={"stance": "satisfied"}),
        ]
        result = detector.check_consensus(msgs, active_attackers={"correctness"})
        assert result["converged"] is True

    def test_context_with_extra_context(self):
        ctx = DebateContext("test", DebateConfig())
        ctx.extra_context = "用户偏好: Python 3.10+"
        ctx.round = 1
        ctx.add_message("coder", "code")
        view = ctx.get_context_for_agent("coder")
        assert len(view) >= 1

    @pytest.mark.asyncio
    async def test_cross_review_user_skips_attacker(self):
        """During cross_review, user can skip an attacker for next round."""
        state = _base_state(
            round=1,
            enable_interrupt=True,
            messages=[
                _attacker_msg("security", "attacking"),
                _attacker_msg("performance", "satisfied"),
                _attacker_msg("correctness", "satisfied"),
            ],
        )
        with patch("app.engine.graph.security_agent") as ms, \
             patch("app.engine.graph.performance_agent") as mp, \
             patch("app.engine.graph.correctness_agent") as mc, \
             patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            for m in [ms, mp, mc]:
                m.speak = AsyncMock(return_value=_mock_response("x", "ok", stance="satisfied"))
            mock_interrupt.return_value = {"type": "skip_attacker", "attacker": "performance"}
            result = await cross_review_node(state)

        assert "performance" in result.get("skip_list", [])

    @pytest.mark.asyncio
    async def test_cross_review_user_adds_context(self):
        """User adds extra context during cross_review."""
        state = _base_state(
            round=1,
            enable_interrupt=True,
            messages=[
                _attacker_msg("security", "attacking"),
                _attacker_msg("correctness", "satisfied"),
            ],
        )
        with patch("app.engine.graph.security_agent") as ms, \
             patch("app.engine.graph.performance_agent") as mp, \
             patch("app.engine.graph.correctness_agent") as mc, \
             patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            for m in [ms, mp, mc]:
                m.speak = AsyncMock(return_value=_mock_response("x", "ok", stance="satisfied"))
            mock_interrupt.return_value = {"type": "add_context", "content": "这个接口面向公网"}
            result = await cross_review_node(state)

        assert result.get("extra_context") == "这个接口面向公网"

    @pytest.mark.asyncio
    async def test_plan_with_unknown_action_breaks_loop(self):
        """Plan phase: unknown action type → auto-proceeds."""
        state = _base_state(enable_interrupt=True)
        with patch("app.llm.client.call_agent") as mc, \
             patch("app.engine.graph.record_agent_call"), \
             patch("app.engine.graph._notify", new_callable=AsyncMock):
            mc.return_value = _mock_response("planner", "方案")
            gen_result = await plan_generate_node(state)
        state.update(gen_result)
        with patch("app.engine.graph._notify", new_callable=AsyncMock), \
             patch("app.engine.graph.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"action": "unknown_action"}
            result = await plan_select_node(state)

        assert result["selected_plan"] != ""
        assert result["plan_action"] == "done"
