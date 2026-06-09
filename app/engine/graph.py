"""
LangGraph state graph definition for AutoJudge debate flow.

Uses three key LangGraph capabilities:
1. Parallel branches (three Attackers run concurrently then join)
2. Checkpoint (resume from any step after disconnect)
3. Interrupt (user intervention between rounds — POST auto-skips)

Entry point: run_debate_with_graph() wraps the graph with Memory/TestRunner/
ComplexityRouter pre/post-processing, then runs the compiled graph.
"""

from __future__ import annotations

import asyncio
import logging
import operator
import time
import uuid
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.types import interrupt, Command
from langgraph.errors import GraphInterrupt

from app.config import settings


def _merge_messages(left: list[dict], right: list[dict]) -> list[dict]:
    """Reducer: append new messages to existing list (handles parallel fan-in)."""
    return left + right


def _max_int(left: int, right: int) -> int:
    """Reducer: take the higher budget_spent value from parallel nodes."""
    return max(left, right)


def _merge_dicts(left: dict, right: dict) -> dict:
    """Reducer: merge dicts from parallel nodes (right overwrites left on conflict)."""
    if not isinstance(left, dict):
        left = {} if not left else (json.loads(left) if isinstance(left, str) else {})
    if not isinstance(right, dict):
        right = {} if not right else (json.loads(right) if isinstance(right, str) else {})
    merged = dict(left)
    for k, v in right.items():
        if k in merged and isinstance(merged[k], (int, float)) and isinstance(v, (int, float)):
            merged[k] = merged[k] + v
        else:
            merged[k] = v
    return merged

from app.llm.client import set_stream_callback
from app.agents.coder import CoderAgent
from app.agents.security_attacker import SecurityAttacker
from app.agents.performance_attacker import PerformanceAttacker
from app.agents.correctness_attacker import CorrectnessAttacker
from app.agents.judge import JudgeAgent
from app.agents.arbitrator import ArbitratorAgent
from app.engine.context import DebateContext, DebateConfig, DebateMessage
from app.engine.budget import BudgetManager
from app.engine.consensus import ConsensusDetector
from app.engine.requirement_parser import parse_requirement
from app.engine.complexity_router import route_complexity, get_debate_config
from app.engine.test_runner import TestRunner
from app.memory.attack_knowledge import AttackKnowledgeBase
from app.memory.user_preferences import UserPreferenceStore
from app.memory.fix_patterns import FixPatternStore
from app.tracing.metrics import record_debate_complete, record_agent_call
from app.api.models.response import (
    DebateResult,
    DebateSummary,
    RiskAssessment,
    DebateMetrics,
    QualityReport,
)

logger = logging.getLogger(__name__)

# ─── Progress callback registry (concurrent-safe via contextvars) ─

import contextvars

_progress_callback: contextvars.ContextVar[callable | None] = contextvars.ContextVar(
    '_progress_callback', default=None
)


async def _notify(event: dict):
    cb = _progress_callback.get(None)
    if cb:
        try:
            await cb(event)
        except Exception:
            pass


async def _notify_budget(budget: 'BudgetManager', phase: str, agent: str):
    """Push real-time token budget snapshot to the frontend."""
    await _notify({
        "type": "budget_update",
        "spent": budget.spent,
        "total": budget.total,
        "phase": phase,
        "agent": agent,
        "by_agent": dict(budget.by_agent),
        "cache_read": budget.cache_stats.get("read", 0),
        "cache_creation": budget.cache_stats.get("creation", 0),
    })


AGENT_ESTIMATED_SECONDS = {
    "coder": 120,
    "security": 70,
    "performance": 70,
    "correctness": 70,
    "judge": 25,
    "arbitrator": 40,
    "planner": 35,
    "cross_review": 15,
}


def _make_stream_cb(agent_name: str):
    """Create a streaming callback that sends text deltas to the frontend."""
    async def _on_stream(delta: str):
        await _notify({"type": "stream", "agent": agent_name, "delta": delta})
    return _on_stream


# ─── State ──────────────────────────────────────────────────────────────────

class DebateState(TypedDict):
    requirement: str
    language: str
    framework: str
    current_code: str
    round: int
    max_rounds: int
    messages: Annotated[list[dict], _merge_messages]
    consensus: dict
    skip_list: list[str]
    extra_context: str
    experience_context: str
    preference_context: str
    parsed_requirement: dict
    converged: bool
    budget_spent: Annotated[int, _max_int]
    budget_total: int
    budget_by_agent: Annotated[dict, _merge_dicts]
    budget_by_phase: Annotated[dict, _merge_dicts]
    budget_cache_stats: Annotated[dict, _merge_dicts]
    judge_report: dict
    arbitration_result: dict
    must_fix_items: list[dict]
    convergence_reason: str
    selected_plan: str
    plan_content: str
    plan_round: int
    plan_action: str
    config: dict
    round_summaries: dict
    enable_interrupt: bool
    retry_count: int
    user_decision: str


# ─── Shared agent instances ─────────────────────────────────────────────────

coder_agent = CoderAgent()
security_agent = SecurityAttacker()
performance_agent = PerformanceAttacker()
correctness_agent = CorrectnessAttacker()
judge_agent = JudgeAgent()
arbitrator_agent = ArbitratorAgent()
consensus_detector = ConsensusDetector()


# ─── Helpers ────────────────────────────────────────────────────────────────

def _build_context(state: DebateState) -> tuple[DebateContext, BudgetManager]:
    config = DebateConfig(**state.get("config", {}))
    ctx = DebateContext(state["requirement"], config)
    ctx.round = state["round"]
    ctx.current_code = state.get("current_code", "")
    ctx.skip_list = state.get("skip_list", [])
    ctx.extra_context = state.get("extra_context", "")
    ctx.experience_context = state.get("experience_context", "")
    ctx.preference_context = state.get("preference_context", "")
    ctx.parsed_requirement = state.get("parsed_requirement")

    for msg_dict in state.get("messages", []):
        ctx.messages.append(
            DebateMessage(
                agent=msg_dict["agent"],
                content=msg_dict["content"],
                round=msg_dict.get("round", 0),
                code=msg_dict.get("code"),
                structured=msg_dict.get("structured"),
            )
        )

    ctx.round_summaries = dict(state.get("round_summaries", {}))

    budget = BudgetManager(state.get("budget_total", 100_000))
    budget.spent = state.get("budget_spent", 0)
    raw_by_agent = state.get("budget_by_agent", {})
    budget.by_agent = dict(raw_by_agent) if isinstance(raw_by_agent, dict) else {}
    raw_by_phase = state.get("budget_by_phase", {})
    budget.by_phase = dict(raw_by_phase) if isinstance(raw_by_phase, dict) else {}
    raw_cache = state.get("budget_cache_stats", {"read": 0, "creation": 0})
    budget.cache_stats = dict(raw_cache) if isinstance(raw_cache, dict) else {"read": 0, "creation": 0}

    return ctx, budget


# ─── Graph nodes ────────────────────────────────────────────────────────────

PLAN_PHASE_PROMPT = """根据以下需求，设计恰好 2 个不同方向的实现方案。

**必须严格按以下格式输出，不要偏离：**

## 方案 A：「简短标签」

**技术选型**
- 框架：...
- 数据库/存储：...
- 认证/加密：...
- 其他关键依赖：...

**核心流程**（3-5 步，每步一句话）
1. ...
2. ...
3. ...

**安全设计**
- ...（2-3 条关键安全措施）

**不包含**
- ...（明确列出本方案不涵盖的功能）

## 方案 B：「简短标签」

（与方案 A 相同格式，但必须是不同的技术路线）

---

重要：
- 两个方案必须都完整输出，不能只写一个
- 标签要体现差异（如"轻量级" vs "生产级"，"单体" vs "微服务"）
- 不写代码，只说方案
- 每个小节简洁明了，让用户 10 秒内能看懂差异

需求：{requirement}
{extra_context}"""


async def plan_node(state: DebateState) -> dict:
    """Plan Phase: single interrupt per execution, state-driven iteration."""
    ctx, budget = _build_context(state)

    from app.llm.model_router import get_model_for_agent
    from app.llm.client import call_agent

    plans_content = state.get("plan_content", "")
    plan_round = state.get("plan_round", 0)
    plan_action = state.get("plan_action", "")
    max_plan_rounds = 7

    if plan_action == "chat" and plans_content:
        await _notify({"type": "phase_change", "phase": "plan"})
        await _notify({"type": "status", "content": "正在根据反馈调整方案..."})
        await _notify({"type": "agent_start", "agent": "coder"})

        user_message = state.get("extra_context", "")
        adjust_prompt = (
            f"用户对方案有调整意见：\n{user_message}\n\n"
            f"请根据用户的反馈重新设计 2 个不同方向的实现方案。"
            f"之前的方案：\n{plans_content}"
        )

        start = time.monotonic()
        response = await coder_agent.speak(ctx, adjust_prompt, budget)
        record_agent_call("coder", response.tokens_used, time.monotonic() - start)
        await _notify_budget(budget, "plan", "coder")
        plans_content = response.content
    else:
        await _notify({"type": "phase_change", "phase": "plan"})
        await _notify({"type": "status", "content": "Coder 正在设计方案..."})
        await _notify({"type": "agent_start", "agent": "coder"})

        extra = state.get("extra_context", "")
        prompt = PLAN_PHASE_PROMPT.format(
            requirement=state["requirement"],
            extra_context=f"补充信息：{extra}" if extra else "",
        )

        start = time.monotonic()
        system = (
            "你是方案设计师。根据用户需求设计 2 个不同方向的实现方案。"
            "不写代码，只说方案。每个方案说明技术选型、核心流程、安全考虑、不包含什么。"
        )
        messages = [{"role": "user", "content": prompt}]
        response = await call_agent(
            agent="planner",
            system_prompt=system,
            messages=messages,
            model=get_model_for_agent("planner"),
            max_tokens=await budget.get_max_tokens("coder"),
        )
        await budget.record("coder", response.tokens_used)
        record_agent_call("coder", response.tokens_used, time.monotonic() - start)
        await _notify_budget(budget, "plan", "planner")
        plans_content = response.content

        # Check if both plans were generated — retry if only one
        import re as _re
        plan_headers = _re.findall(r"##\s*方案\s*[A-Za-z]", plans_content)
        if len(plan_headers) < 2:
            logger.warning("plan_incomplete only=%d plans, retrying", len(plan_headers))
            retry_msg = [{"role": "user", "content": (
                f"{prompt}\n\n"
                "注意：你上次只给出了 1 个方案。请务必给出 2 个完整方案（方案 A 和方案 B），"
                "两个方案必须都有技术选型、核心流程、安全设计、不包含。"
            )}]
            retry_resp = await call_agent(
                agent="planner", system_prompt=system, messages=retry_msg,
                model=get_model_for_agent("planner"),
                max_tokens=await budget.get_max_tokens("coder"),
            )
            await budget.record("coder", retry_resp.tokens_used)
            if _re.findall(r"##\s*方案\s*[A-Za-z]", retry_resp.content).__len__() >= 2:
                plans_content = retry_resp.content

    await _notify({"type": "plan_proposal", "content": plans_content})

    selected_plan = plans_content

    if state.get("enable_interrupt") and plan_round < max_plan_rounds:
        hint = ""
        if plan_round == 3:
            hint = "\n\n💡 已调整 3 轮方案。建议先选一个开始——后续辩论阶段还可以继续优化。"
        elif plan_round >= 5:
            hint = "\n\n⚠️ 方案讨论已进行多轮。建议尽快选择一个方案开始。"

        user_input = interrupt({
            "type": "plan_review",
            "content": plans_content + hint,
            "round": plan_round,
            "max_rounds": max_plan_rounds,
        })

        if user_input and isinstance(user_input, dict):
            action = user_input.get("action", "")
            if action == "select":
                selected_plan = user_input.get("plan_content", plans_content)
            elif action == "chat":
                return {
                    "plan_content": plans_content,
                    "plan_round": plan_round + 1,
                    "plan_action": "chat",
                    "extra_context": user_input.get("message", ""),
                    "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
                }

    plan_msg = {
        "agent": "coder",
        "content": f"[方案设计] {plans_content}",
        "round": 0,
    }
    await _notify({"type": "message", **plan_msg})

    return {
        "selected_plan": selected_plan,
        "plan_content": plans_content,
        "plan_action": "done",
        "messages": [plan_msg],
        "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
    }



async def coder_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)
    ctx.round = state["round"] + 1

    if ctx.round == 1:
        await _notify({"type": "phase_change", "phase": "coding"})
    await _notify({"type": "agent_start", "agent": "coder", "estimated_seconds": AGENT_ESTIMATED_SECONDS.get("coder", 60)})

    if ctx.round == 1:
        selected_plan = state.get("selected_plan", "")
        if selected_plan:
            prompt = (
                f"根据以下需求和确认的方案生成 **完整的、可直接运行的** 代码：\n{ctx.requirement}\n\n"
                f"确认的方案：\n{selected_plan}\n\n"
                "严格要求：\n"
                "1. 必须是完整实现，不是 demo、stub、示例片段或 PoC\n"
                "2. 必须包含需求中提到的所有核心功能（如认证、加密、数据库操作等）\n"
                "3. 代码必须可以直接运行，包含所有 import 和必要的类/函数定义\n"
                "4. 提交前用 run_code_snippet 自测确认能正常运行\n"
            )
        else:
            prompt = (
                f"根据以下需求生成 **完整的、可直接运行的** 代码：\n{ctx.requirement}\n\n"
                "严格要求：\n"
                "1. 必须是完整实现，不是 demo 或示例片段\n"
                "2. 包含所有核心功能、import 和类/函数定义\n"
                "3. 提交前用 run_code_snippet 自测确认能正常运行\n"
            )
        if ctx.extra_context:
            prompt += f"\n\n补充需求：{ctx.extra_context}"
    else:
        current = state.get("current_code", "")

        # Build structured finding list with IDs for Coder to reference
        last_attacker_msgs = [
            m for m in state.get("messages", [])
            if m.get("round") == state["round"]
            and m["agent"] in ("security", "performance", "correctness")
        ]
        finding_list_lines = []
        fix_descriptions = []
        for m in last_attacker_msgs:
            s = m.get("structured")
            if s and isinstance(s, dict):
                for fi, f in enumerate(s.get("findings", [])):
                    if not isinstance(f, dict):
                        continue
                    fid = f.get("finding_id", f"{m['agent'].upper()}-{str(fi+1).zfill(3)}")
                    sev = f.get("severity", "?")
                    cat = f.get("category", "?")
                    desc = f.get("description", "")
                    finding_list_lines.append(f"  {fid}: [{sev}] {cat} — {desc[:120]}")
                    fix_descriptions.append(desc)

        prompt = (
            "请逐条回应上一轮 Attacker 提出的问题。\n"
            "对每个攻击：如果合理 → accept_and_fix 并修复代码；如果不合理 → rebut_with_evidence 并给出证据。\n\n"
        )
        if finding_list_lines:
            prompt += "需要回应的问题（finding_ref 必须使用下面的 ID，如 SECURITY-001）：\n"
            prompt += "\n".join(finding_list_lines)
            prompt += "\n\n"
        prompt += (
            "修复后必须通过 updated_code 提交**完整的**新版代码（在上一版基础上修改，不要重写或提交测试脚本）。\n"
            "提交前请用 run_code_snippet 自测修复后的代码。"
        )
        if current:
            prompt += f"\n\n你当前的完整代码如下（在此基础上修改）：\n```\n{current}\n```"

        if fix_descriptions:
            fix_patterns_store = FixPatternStore()
            for desc in fix_descriptions[:3]:
                fixes = await fix_patterns_store.retrieve_fixes(desc, top_k=2)
                if fixes:
                    prompt += f"\n\n历史修复参考（{desc[:40]}）：\n" + "\n".join(fixes[:2])

    start = time.monotonic()
    set_stream_callback(_make_stream_cb("coder"))
    response = await coder_agent.speak(ctx, prompt, budget)
    set_stream_callback(None)
    record_agent_call("coder", response.tokens_used, time.monotonic() - start)
    await _notify_budget(budget, "code_gen" if ctx.round == 1 else "debate", "coder")

    # --- Code quality gate: reject demo/stub/test scripts ---
    prev_code = state.get("current_code", "")
    new_code = response.code or ""
    MIN_FIRST_CODE_LEN = 200

    if ctx.round == 1 and new_code and len(new_code) < MIN_FIRST_CODE_LEN:
        logger.warning("coder_code_too_short round=1 len=%d, retrying", len(new_code))
        retry_prompt = (
            f"你提交的代码只有 {len(new_code)} 字节，这不是完整实现。\n"
            "请重新生成**完整的、包含所有核心功能的**代码。\n"
            "不要提交 demo、示例片段或测试脚本。"
        )
        set_stream_callback(_make_stream_cb("coder"))
        response = await coder_agent.speak(ctx, retry_prompt, budget)
        set_stream_callback(None)
        new_code = response.code or new_code

    if ctx.round > 1 and prev_code and new_code and len(new_code) < len(prev_code) * 0.3:
        logger.warning("coder_code_regressed round=%d prev=%d new=%d, using prev",
                        ctx.round, len(prev_code), len(new_code))
        new_code = prev_code

    await _notify({"type": "stream_end", "agent": "coder"})
    elapsed_s = round(time.monotonic() - start, 1)
    has_code = bool(new_code and len(new_code) > 50)
    await _notify({
        "type": "agent_done",
        "agent": "coder",
        "elapsed_seconds": elapsed_s,
        "has_code": has_code,
        "code_lines": len(new_code.split("\n")) if new_code else 0,
    })
    new_msg = {
        "agent": "coder",
        "content": response.content,
        "round": ctx.round,
        "code": new_code or None,
        "structured": response.structured,
    }
    await _notify({"type": "message", **new_msg})
    await _notify({"type": "round_start", "round": ctx.round})

    return {
        "round": ctx.round,
        "current_code": new_code or state.get("current_code", ""),
        "messages": [new_msg],
        "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
    }


async def _attacker_node(
    state: DebateState, agent_instance, agent_name: str
) -> dict:
    if agent_name in state.get("skip_list", []):
        return {}

    await _notify({"type": "agent_start", "agent": agent_name, "estimated_seconds": AGENT_ESTIMATED_SECONDS.get(agent_name, 60)})
    ctx, budget = _build_context(state)

    current_code = state.get("current_code", "")
    line_count = len(current_code.split("\n")) if current_code else 0

    if state["round"] <= 1:
        prompt = (
            "审查 Coder 提交的代码，从你的专业角度找出问题。\n\n"
            "**关于行号（极其重要）**：\n"
            f"当前代码共 {line_count} 行。每个 finding 必须填写 line_start 和 line_end（从 1 开始的行号）。\n"
            "例如：问题在第 15-20 行，则 line_start=15, line_end=20。单行问题则两者相同。\n"
            "没有行号的 finding 会被系统自动丢弃，所以务必填写。"
        )
    else:
        prompt = (
            "审查 Coder 的最新修复。如果之前的问题已修复，确认。\n"
            "如果有新问题，指出并标注 line_start/line_end 行号。\n"
            f"当前代码共 {line_count} 行，行号从 1 开始。\n"
            "如果没有新问题了，stance 设为 satisfied。"
        )

    try:
        start = time.monotonic()
        set_stream_callback(_make_stream_cb(agent_name))
        response = await agent_instance.speak(ctx, prompt, budget)
        set_stream_callback(None)
        record_agent_call(agent_name, response.tokens_used, time.monotonic() - start)
        await _notify_budget(budget, "debate", agent_name)
        await _notify({"type": "stream_end", "agent": agent_name})
        structured = response.structured
        if not structured or not isinstance(structured, dict):
            content_lower = response.content.lower()
            has_attack_content = any(kw in content_lower for kw in [
                "漏洞", "bug", "错误", "问题", "风险", "注入", "泄露", "溢出", "越界",
                "vulnerability", "injection", "error", "issue", "risk", "leak", "overflow",
                "sql", "xss", "csrf", "o(n²)", "o(n^2)", "内存", "死锁", "竞态",
            ])
            inferred = "attacking" if has_attack_content else "satisfied"
            structured = {
                "stance": inferred,
                "message": response.content,
                "findings": [],
            }
            logger.warning("attacker_%s_no_structured round=%d, inferred stance=%s (attack_keywords=%s)",
                           agent_name, state["round"], inferred, has_attack_content)

        # --- Post-process findings: assign IDs + fill missing line_start ---
        code_lines = (state.get("current_code") or "").split("\n")
        for i, f in enumerate(structured.get("findings", [])):
            if not isinstance(f, dict):
                continue
            f["finding_id"] = f"{agent_name.upper()}-{i + 1:03d}"

            if not f.get("line_start") and code_lines:
                desc_lower = (f.get("description", "") + " " + f.get("category", "")).lower()
                keywords = [w for w in desc_lower.split() if len(w) >= 4 and w.isalpha()]
                for ln_idx, line in enumerate(code_lines):
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in keywords[:5]):
                        f["line_start"] = ln_idx + 1
                        f["line_end"] = f.get("line_end") or (ln_idx + 1)
                        break

        findings_count = len(structured.get("findings", []))
        stance = structured.get("stance", "unknown")
        elapsed_s = round(time.monotonic() - start, 1)
        await _notify({
            "type": "agent_done",
            "agent": agent_name,
            "elapsed_seconds": elapsed_s,
            "stance": stance,
            "findings_count": findings_count,
        })

        new_msg = {
            "agent": agent_name,
            "content": response.content,
            "round": state["round"],
            "structured": structured,
        }
        await _notify({"type": "message", **new_msg})
        return {
            "messages": [new_msg],
            "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
        }
    except Exception as e:
        logger.warning("graph_%s_failed error=%s", agent_name, e, exc_info=True)
        set_stream_callback(None)
        await _notify({"type": "stream_end", "agent": agent_name})

        error_short = str(e)[:200]
        is_proxy_error = any(kw in error_short.lower() for kw in ["502", "503", "400", "proxy", "timeout", "upstream"])
        await _notify({
            "type": "agent_error",
            "agent": agent_name,
            "error": error_short,
            "is_proxy_error": is_proxy_error,
        })

        return {
            "messages": [{
                "agent": agent_name,
                "content": f"[系统错误] {agent_name} 调用失败: {error_short}",
                "round": state["round"],
                "structured": {
                    "stance": "error",
                    "message": error_short,
                    "findings": [],
                },
            }],
        }


async def security_node(state: DebateState) -> dict:
    return await _attacker_node(state, security_agent, "security")


async def performance_node(state: DebateState) -> dict:
    return await _attacker_node(state, performance_agent, "performance")


async def correctness_node(state: DebateState) -> dict:
    return await _attacker_node(state, correctness_agent, "correctness")


def _build_structured_findings_summary(round_msgs: list[dict], exclude_agent: str) -> str:
    """
    Layer 3: Structured Summary Injection
    从其他攻击者的结构化输出中提取 findings，
    以 [SEVERITY] category: description 格式注入，不传完整自然语言。
    """
    lines = []
    for m in round_msgs:
        if m["agent"] == exclude_agent:
            continue
        structured = m.get("structured")
        if not structured or not isinstance(structured, dict):
            if m.get("content"):
                lines.append(f"[{m['agent'].upper()}] {m['content'][:200]}")
            continue
        findings = structured.get("findings", [])
        stance = structured.get("stance", "unknown")
        if findings:
            for f in findings:
                if not isinstance(f, dict):
                    continue
                sev = f.get("severity", "unknown").upper()
                cat = f.get("category", "")
                desc = f.get("description", "")
                lines.append(f"[{m['agent'].upper()}] [{sev}] {cat}: {desc}")
        elif stance == "attacking":
            msg_text = structured.get("message", "有顾虑但未提供具体 findings")
            lines.append(f"[{m['agent'].upper()}] [MEDIUM] {msg_text[:200]}")
        else:
            lines.append(f"[{m['agent'].upper()}] stance={stance}，无新发现")
    return "\n".join(lines)


async def cross_review_node(state: DebateState) -> dict:
    """
    Layer 3 实现：交叉审阅时注入结构化 findings 摘要，
    而不是其他攻击者的完整自然语言发言。
    """
    ctx, budget = _build_context(state)
    current_round = state["round"]

    round_msgs = [
        m
        for m in state.get("messages", [])
        if m.get("round") == current_round
        and m["agent"] in ("security", "performance", "correctness")
    ]

    config = state.get("config", {})
    if config.get("skip_cross_review") or len(round_msgs) < 2:
        if current_round > 2:
            await ctx.compress_early_rounds()
        result = _check_and_return_consensus(state, round_msgs)
        result["round_summaries"] = dict(ctx.round_summaries)
        return result

    agents = {
        "security": security_agent,
        "performance": performance_agent,
        "correctness": correctness_agent,
    }

    new_cross_msgs = []

    errored_agents = {
        m["agent"] for m in round_msgs
        if (m.get("structured") or {}).get("stance") == "error"
    }
    active = [
        (name, agent) for name, agent in agents.items()
        if name not in state.get("skip_list", [])
        and name not in errored_agents
    ]

    async def safe_cross(name, agent):
        try:
            others_findings = _build_structured_findings_summary(round_msgs, exclude_agent=name)
            cross_prompt = (
                f"以下是其他 Attacker 本轮的结构化发现：\n{others_findings}\n\n"
                "请补充你认为重要但对方遗漏的观点，或对对方的发现表示支持/质疑。"
                "如果没有补充，直接确认。"
            )
            return name, await agent.speak(ctx, cross_prompt, budget)
        except Exception as e:
            logger.warning("cross_review_%s_failed error=%s", name, e)
            return name, None

    cross_results = await asyncio.gather(
        *[safe_cross(n, a) for n, a in active]
    )

    for name, response in cross_results:
        if response and response.content.strip():
            new_cross_msgs.append({
                "agent": name,
                "content": f"[交叉审阅] {response.content}",
                "round": current_round,
                "structured": response.structured,
            })

    updated_state = {**state, "messages": new_cross_msgs}

    if state.get("enable_interrupt"):
        user_input = interrupt({
            "type": "round_complete",
            "round": current_round,
            "can_skip": ["security", "performance", "correctness"],
        })
        if user_input and isinstance(user_input, dict):
            if user_input.get("type") == "skip_attacker":
                skip_list = list(state.get("skip_list", []))
                skip_list.append(user_input["attacker"])
                updated_state["skip_list"] = skip_list
            elif user_input.get("type") == "add_context":
                updated_state["extra_context"] = user_input.get("content", "")

    if current_round > 2:
        await ctx.compress_early_rounds()
        updated_state["round_summaries"] = dict(ctx.round_summaries)

    consensus_msgs = round_msgs + new_cross_msgs
    result = _check_and_return_consensus(updated_state, consensus_msgs)
    result["round_summaries"] = dict(ctx.round_summaries)
    return result


def _check_and_return_consensus(
    state: dict, round_msgs: list[dict]
) -> dict:
    seen_agents: set[str] = set()
    latest_per_agent: dict[str, dict] = {}
    for m in round_msgs:
        if m["agent"] in ("security", "performance", "correctness"):
            latest_per_agent[m["agent"]] = m

    debate_msgs = [
        DebateMessage(
            agent=m["agent"],
            content=m["content"],
            round=m.get("round", 0),
            structured=m.get("structured"),
        )
        for m in latest_per_agent.values()
    ]

    skip_list = set(state.get("skip_list", []))
    active_attackers = {"security", "performance", "correctness"} - skip_list
    result = consensus_detector.check_consensus(debate_msgs, active_attackers)

    update = {
        "consensus": result,
        "converged": result.get("converged", False),
        "budget_spent": state.get("budget_spent", 0),
    }
    if state.get("messages"):
        update["messages"] = state["messages"]
    if "skip_list" in state:
        update["skip_list"] = state["skip_list"]
    if "extra_context" in state:
        update["extra_context"] = state["extra_context"]
    return update


def check_consensus_edge(state: DebateState) -> str:
    if state.get("converged"):
        return "converged"

    # If ALL attackers failed this round (stance=error or no messages), stop immediately
    current_round = state.get("round", 0)
    skip_list = set(state.get("skip_list", []))
    active_attackers = {"security", "performance", "correctness"} - skip_list
    round_attacker_msgs = [
        m for m in state.get("messages", [])
        if m.get("round") == current_round
        and m["agent"] in active_attackers
    ]
    if active_attackers and round_attacker_msgs:
        all_errored = all(
            (m.get("structured") or {}).get("stance") == "error"
            for m in round_attacker_msgs
        )
        if all_errored:
            return "budget_exceeded"

    if active_attackers and not round_attacker_msgs:
        return "budget_exceeded"

    budget_total = state.get("budget_total", 100_000)
    budget_spent = state.get("budget_spent", 0)
    if budget_spent >= budget_total * 0.85:
        return "budget_exceeded"

    max_rounds = state.get("max_rounds", 5)
    if state.get("round", 0) >= max_rounds:
        return "budget_exceeded"

    return "continue"



def _extract_unresolved_disputes(state: DebateState) -> list[dict]:
    """Extract unresolved disputes from debate messages."""
    disputes = []
    last_round = state.get("round", 0)

    for msg in state.get("messages", []):
        if msg.get("round", 0) < last_round:
            continue
        if msg["agent"] in ("security", "performance", "correctness"):
            structured = msg.get("structured")
            if not structured or not isinstance(structured, dict):
                continue
            if structured.get("stance") != "attacking":
                continue
            findings = structured.get("findings", [])
            if findings:
                for finding in findings:
                    if not isinstance(finding, dict):
                        continue
                    disputes.append({
                        "attacker": msg["agent"],
                        "finding": finding.get("description", ""),
                        "severity": finding.get("severity", "unknown"),
                        "test_input": finding.get("test_input"),
                        "coder_response": _find_coder_response(state, finding),
                    })
            else:
                disputes.append({
                    "attacker": msg["agent"],
                    "finding": structured.get("message", "Attacker 表示仍有顾虑但未提供具体 findings"),
                    "severity": "medium",
                    "test_input": None,
                    "coder_response": "未回应",
                })
    return disputes


SECURITY_REDLINE_CATEGORIES = {
    "sql_injection", "rce", "command_injection",
    "auth_bypass", "path_traversal", "xss",
    "sql injection", "remote code execution",
}


def _security_redline_allows(ruling: dict, new_verdict: str) -> bool:
    """Critical security issues cannot be downgraded by user override."""
    if ruling.get("re_assessed_severity") != "critical":
        return True
    dispute_id = ruling.get("dispute_id", "").lower()
    reasoning = ruling.get("reasoning", "").lower()
    is_security_redline = any(
        cat in dispute_id or cat in reasoning
        for cat in SECURITY_REDLINE_CATEGORIES
    )
    if is_security_redline and new_verdict in ("dismissed", "acknowledged", "deferred"):
        return False
    return True


def _needs_human_review(state: dict) -> bool:
    """Check if the final result requires human review."""
    arb = state.get("arbitration_result")
    if not arb or not isinstance(arb, dict):
        return False
    rulings = arb.get("rulings", [])
    needs_human_count = sum(1 for r in rulings if r.get("verdict") == "needs_human")
    must_fix_count = sum(1 for r in rulings if r.get("verdict") == "must_fix")
    has_unfixed_critical = any(
        r.get("re_assessed_severity") == "critical" and r.get("verdict") == "must_fix"
        for r in rulings
    )
    return needs_human_count > 0 or must_fix_count > 3 or has_unfixed_critical


def _find_coder_response(state: DebateState, finding: dict) -> str:
    """Find Coder's response to a specific finding."""
    for msg in reversed(state.get("messages", [])):
        if msg["agent"] == "coder" and msg.get("structured"):
            structured = msg["structured"]
            if isinstance(structured, dict):
                for resp in structured.get("responses", []):
                    if finding.get("description", "") in resp.get("explanation", ""):
                        action = resp.get("action", "?")
                        explanation = resp.get("explanation", "")
                        return f"[{action}] {explanation}"
    return "未回应"


async def arbitration_node(state: DebateState) -> dict:
    """Arbitrator intervenes when debate fails to converge."""
    ctx, budget = _build_context(state)

    disputes = _extract_unresolved_disputes(state)

    if not disputes:
        return {
            "converged": True,
            "convergence_reason": "仲裁判定：无实质未解决争议，等效收敛",
            "arbitration_result": {},
            "must_fix_items": [],
        }

    await _notify({"type": "phase_change", "phase": "arbitration"})
    await _notify({
        "type": "status",
        "content": f"辩论未收敛，Arbitrator 正在仲裁 {len(disputes)} 条争议...",
    })

    arbitration_result = await arbitrator_agent.arbitrate(ctx, budget, disputes)
    await _notify_budget(budget, "arbitration", "arbitrator")

    await _notify({
        "type": "arbitration_complete",
        "disputes_count": len(disputes),
        "overall_verdict": arbitration_result.get("overall_verdict"),
        "summary": arbitration_result.get("summary", ""),
    })

    # HITL: let user review arbitration ruling
    if state.get("enable_interrupt"):
        user_feedback = interrupt({
            "type": "arbitration_review",
            "rulings": arbitration_result.get("rulings", []),
            "overall_verdict": arbitration_result.get("overall_verdict"),
            "summary": arbitration_result.get("summary", ""),
        })
        if user_feedback and isinstance(user_feedback, dict):
            overrides = user_feedback.get("overrides", {})
            for ruling in arbitration_result.get("rulings", []):
                did = ruling.get("dispute_id", "")
                override = overrides.get(did)
                if override and override.get("action") in ("upgrade", "downgrade", "dismiss"):
                    new_verdict = override.get("new_verdict", ruling["verdict"])
                    if not _security_redline_allows(ruling, new_verdict):
                        ruling["reasoning"] += "\n[安全红线] 用户尝试降级被拒绝"
                        continue
                    ruling["verdict"] = new_verdict
                    ruling["reasoning"] += f"\n[用户调整] → {new_verdict}"

    overall = arbitration_result.get("overall_verdict", "not_deliverable")
    rulings = arbitration_result.get("rulings", [])
    must_fix = [r for r in rulings if r.get("verdict") == "must_fix"]

    if overall == "deliverable" or not must_fix:
        return {
            "converged": True,
            "convergence_reason": f"仲裁裁决：代码可交付（{len(disputes)} 条争议已裁决）",
            "arbitration_result": arbitration_result,
            "must_fix_items": [],
        }

    if overall == "fix_then_deliver" and len(must_fix) <= 3:
        has_critical = any(
            r.get("re_assessed_severity") == "critical" for r in must_fix
        )
        if not has_critical:
            return {
                "converged": False,
                "convergence_reason": "仲裁裁决：需修复后交付",
                "arbitration_result": arbitration_result,
                "must_fix_items": must_fix,
            }

    return {
        "converged": True,
        "convergence_reason": "仲裁裁决：建议人工审查",
        "arbitration_result": arbitration_result,
        "must_fix_items": [],
    }


def _arbitration_edge(state: DebateState) -> str:
    must_fix = state.get("must_fix_items", [])
    if must_fix:
        return "fix"
    return "deliver"


async def final_fix_node(state: DebateState) -> dict:
    """Coder fixes must_fix items after arbitration."""
    ctx, budget = _build_context(state)
    must_fix_items = state.get("must_fix_items", [])

    if not must_fix_items:
        return {"converged": True, "convergence_reason": "无需修复"}

    fix_list = "\n".join(
        f"{i+1}. [{item.get('re_assessed_severity', '?')}] {item.get('reasoning', '')}"
        for i, item in enumerate(must_fix_items)
    )

    fix_refs = []
    fix_pattern_store = FixPatternStore()
    for item in must_fix_items:
        desc = item.get("reasoning", "")
        if desc:
            fixes = await fix_pattern_store.retrieve_fixes(desc, top_k=2)
            if fixes:
                fix_refs.append(f"[{desc[:40]}] 历史修复参考：\n" + "\n".join(fixes[:2]))

    fix_prompt = (
        f"仲裁裁决要求你修复以下 {len(must_fix_items)} 个问题。\n"
        f"只修复这些具体问题，不要做其他改动。\n"
        f"提交前请用 run_code_snippet 自测修复后的代码。\n\n"
        f"{fix_list}"
    )
    if fix_refs:
        fix_prompt += "\n\n" + "\n\n".join(fix_refs)

    STRATEGY_ANGLES = [
        "换一种数据结构或算法来实现同样功能",
        "换一个实现层级（如从函数级改为模块级或路由级）",
        "换一种依赖库来解决问题",
        "简化需求范围，只修核心部分",
    ]
    strategy_idx = 0
    new_code = state.get("current_code", "")
    all_fix_msgs: list[dict] = []

    for attempt in range(3):
        current_prompt = fix_prompt if attempt == 0 else (
            f"前一次修复失败了。请从不同角度考虑：\n"
            f"策略：{STRATEGY_ANGLES[strategy_idx % len(STRATEGY_ANGLES)]}\n\n"
            f"原始问题：\n{fix_list}\n\n"
            f"提交前请用 run_code_snippet 自测修复后的代码。"
        )

        if attempt > 0 and state.get("enable_interrupt"):
            user_response = interrupt({
                "type": "strategy_review",
                "attempt": attempt + 1,
                "strategy": STRATEGY_ANGLES[strategy_idx % len(STRATEGY_ANGLES)],
                "original_issues": fix_list,
            })
            if user_response and isinstance(user_response, dict):
                if user_response.get("action") == "user_strategy":
                    current_prompt = (
                        f"用户建议的修复思路：{user_response.get('message', '')}\n\n"
                        f"原始问题：\n{fix_list}\n\n"
                        f"请按用户思路修复，提交前用 run_code_snippet 自测。"
                    )

        await _notify({"type": "agent_start", "agent": "coder"})
        await _notify({"type": "fix_progress", "attempt": attempt + 1, "max_attempts": 3})

        start = time.monotonic()
        response = await coder_agent.speak(ctx, current_prompt, budget)
        record_agent_call("coder", response.tokens_used, time.monotonic() - start)
        await _notify_budget(budget, "arbitration", "coder")

        if response.code:
            new_code = response.code
            ctx.current_code = new_code

        fix_msg = {
            "agent": "coder",
            "content": f"[修复 attempt {attempt+1}] {response.content}",
            "round": state["round"] + 1,
            "code": response.code,
            "structured": response.structured,
        }
        await _notify({"type": "message", **fix_msg})
        all_fix_msgs.append(fix_msg)

        if response.code:
            break

        strategy_idx += 1

    # Arbitrator reviews the fix
    await _notify({
        "type": "status",
        "content": "Arbitrator 正在复核修复结果...",
    })

    ctx.current_code = new_code
    reviews = await arbitrator_agent.review_fixes(ctx, budget, must_fix_items)
    await _notify_budget(budget, "arbitration", "arbitrator")

    not_fixed = [r for r in reviews if r.get("status") != "fixed"]

    if not_fixed:
        await _notify({
            "type": "status",
            "content": f"复核发现 {len(not_fixed)} 项未完全修复，Coder 正在补修...",
        })

        not_fixed_desc = "\n".join(
            f"- {r.get('dispute_id', '?')}: {r.get('review_comment', '')}"
            for r in not_fixed
        )
        refix_prompt = (
            f"Arbitrator 复核发现以下 {len(not_fixed)} 项未正确修复：\n"
            f"{not_fixed_desc}\n"
            f"请针对性修复，提交前用 run_code_snippet 自测。"
        )

        start = time.monotonic()
        refix_response = await coder_agent.speak(ctx, refix_prompt, budget)
        record_agent_call("coder", refix_response.tokens_used, time.monotonic() - start)
        await _notify_budget(budget, "arbitration", "coder")

        if refix_response.code:
            new_code = refix_response.code

        refix_msg = {
            "agent": "coder",
            "content": f"[补修] {refix_response.content}",
            "round": state["round"] + 1,
            "code": refix_response.code,
            "structured": refix_response.structured,
        }
        await _notify({"type": "message", **refix_msg})

        return {
            "current_code": new_code,
            "messages": all_fix_msgs + [refix_msg],
            "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
            "converged": True,
            "convergence_reason": "仲裁后修复完成（含补修）",
        }

    return {
        "current_code": new_code,
        "messages": all_fix_msgs,
        "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
        "converged": True,
        "convergence_reason": "仲裁后修复完成",
    }


async def judge_node(state: DebateState) -> dict:
    ctx, budget = _build_context(state)

    await _notify({"type": "phase_change", "phase": "judging"})
    await _notify({"type": "agent_start", "agent": "judge"})

    start = time.monotonic()
    set_stream_callback(_make_stream_cb("judge"))
    report = await judge_agent.summarize(ctx, budget)
    set_stream_callback(None)
    record_agent_call("judge", budget.by_agent.get("judge", 0), time.monotonic() - start)
    await _notify({"type": "stream_end", "agent": "judge"})
    await _notify_budget(budget, "judge", "judge")

    if not report or not report.get("star_rating"):
        prev_report = state.get("judge_report", {})
        if prev_report and prev_report.get("star_rating"):
            logger.warning("judge_report_empty_but_previous_exists, keeping previous report")
            report = prev_report
        else:
            logger.warning("judge_report_empty_no_previous, using fallback defaults")
            report = report or {}
            report.setdefault("star_rating", 3)
            report.setdefault("star_comment", "代码质量评审完成")
            report.setdefault("score_security", 50)
            report.setdefault("score_performance", 50)
            report.setdefault("score_correctness", 50)
            report.setdefault("usage_advice", "建议人工审查代码质量。")
            report.setdefault("resolved_issues", [])
            report.setdefault("unresolved_issues", [])
            report.setdefault("confidence", 0.5)

    new_msg = {
        "agent": "judge",
        "content": report.get("summary", "代码质量评审完成。"),
        "round": state.get("round", 0),
        "structured": report,
    }
    await _notify({"type": "message", **new_msg})

    return {
        "judge_report": report,
        "messages": [new_msg],
        "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
    }


# ─── Resolution loop nodes ────────────────────────────────────────────────

MAX_RESOLUTION_RETRIES = 2
RETRY_BUDGET_RESERVE = 0.15


async def resolution_check_node(state: DebateState) -> dict:
    """Check if Judge found unresolved issues. Route to retry, user decision, or done."""
    judge_report = state.get("judge_report", {})
    unresolved = judge_report.get("unresolved_issues", [])
    retry_count = state.get("retry_count", 0)

    if not unresolved:
        await _notify({
            "type": "status",
            "content": "所有问题已解决，交付完成代码。",
        })
        return {"user_decision": "all_resolved"}

    budget_total = state.get("budget_total", 100_000)
    budget_spent = state.get("budget_spent", 0)
    budget_remaining_ratio = (budget_total - budget_spent) / max(budget_total, 1)
    has_budget = budget_remaining_ratio > RETRY_BUDGET_RESERVE
    can_retry = retry_count < MAX_RESOLUTION_RETRIES and has_budget

    if can_retry:
        await _notify({
            "type": "status",
            "content": (
                f"Judge 发现 {len(unresolved)} 个未解决问题，"
                f"自动进入聚焦修复（第 {retry_count + 1}/{MAX_RESOLUTION_RETRIES} 次）..."
            ),
        })
        return {"user_decision": "auto_retry"}

    await _notify({
        "type": "status",
        "content": (
            f"仍有 {len(unresolved)} 个未解决问题，"
            f"{'重试次数已用完' if retry_count >= MAX_RESOLUTION_RETRIES else '预算不足'}。"
        ),
    })
    return {"user_decision": "needs_user_decision"}


def _resolution_check_edge(state: DebateState) -> str:
    decision = state.get("user_decision", "all_resolved")
    if decision == "all_resolved":
        return "done"
    if decision == "auto_retry":
        return "focused_retry"
    return "user_decision"


async def focused_retry_node(state: DebateState) -> dict:
    """Targeted fix for unresolved issues — only relevant attackers verify."""
    ctx, budget = _build_context(state)
    judge_report = state.get("judge_report", {})
    unresolved = judge_report.get("unresolved_issues", [])
    retry_count = state.get("retry_count", 0)

    await _notify({"type": "phase_change", "phase": "fixing"})

    # Build focused fix prompt from unresolved issues
    issue_list = "\n".join(
        f"{i+1}. {item.get('issue', '')} — 当前状态: {item.get('current_status', '?')} "
        f"(影响: {item.get('impact', '?')})"
        for i, item in enumerate(unresolved)
    )

    fix_prompt = (
        f"Judge 评审发现以下 {len(unresolved)} 个问题仍未解决。\n"
        f"请只针对这些问题修复，不要改动其他部分。\n"
        f"提交前用 run_code_snippet 自测。\n\n"
        f"{issue_list}"
    )

    await _notify({"type": "agent_start", "agent": "coder"})
    start = time.monotonic()
    response = await coder_agent.speak(ctx, fix_prompt, budget)
    record_agent_call("coder", response.tokens_used, time.monotonic() - start)
    await _notify_budget(budget, "debate", "coder")

    new_code = response.code or state.get("current_code", "")
    fix_msg = {
        "agent": "coder",
        "content": f"[聚焦修复 retry {retry_count + 1}] {response.content}",
        "round": state["round"] + 1,
        "code": response.code,
        "structured": response.structured,
    }
    await _notify({"type": "message", **fix_msg})

    # Determine which attackers need to verify (based on unresolved issue categories)
    categories_needed = set()
    for item in unresolved:
        issue_text = (item.get("issue", "") + item.get("suggestion", "")).lower()
        if any(kw in issue_text for kw in ("安全", "注入", "xss", "认证", "密码", "加密", "security")):
            categories_needed.add("security")
        if any(kw in issue_text for kw in ("性能", "复杂度", "内存", "缓存", "performance", "o(n")):
            categories_needed.add("performance")
        if any(kw in issue_text for kw in ("边界", "空", "null", "并发", "逻辑", "correctness")):
            categories_needed.add("correctness")

    if not categories_needed:
        categories_needed = {"correctness"}

    # Run only relevant attackers for verification
    verify_state = {**state, "current_code": new_code, "round": state["round"] + 1}
    agents_map = {
        "security": (security_agent, "security"),
        "performance": (performance_agent, "performance"),
        "correctness": (correctness_agent, "correctness"),
    }

    verify_msgs = [fix_msg]

    async def verify_with_attacker(name, agent_instance):
        verify_prompt = (
            f"Coder 刚刚修复了以下问题，请验证修复是否有效：\n{issue_list}\n\n"
            f"如果问题已解决，stance 设为 satisfied。如果仍有问题，指出。"
        )
        try:
            await _notify({"type": "agent_start", "agent": name})
            s = time.monotonic()
            resp = await agent_instance.speak(ctx, verify_prompt, budget)
            record_agent_call(name, resp.tokens_used, time.monotonic() - s)
            return {
                "agent": name,
                "content": f"[聚焦验证] {resp.content}",
                "round": state["round"] + 1,
                "structured": resp.structured,
            }
        except Exception as e:
            logger.warning("focused_verify_%s_failed error=%s", name, e)
            return None

    verify_results = await asyncio.gather(*[
        verify_with_attacker(name, agents_map[name][0])
        for name in categories_needed
        if name in agents_map
    ])

    for msg in verify_results:
        if msg:
            verify_msgs.append(msg)
            await _notify({"type": "message", **msg})

    return {
        "current_code": new_code,
        "messages": verify_msgs,
        "budget_spent": budget.spent,
                "budget_by_agent": dict(budget.by_agent),
                "budget_by_phase": dict(budget.by_phase),
                "budget_cache_stats": dict(budget.cache_stats),
        "retry_count": retry_count + 1,
        "judge_report": {},
    }


async def user_decision_node(state: DebateState) -> dict:
    """When retries exhausted, let user decide: accept, retry with context, or stop."""
    judge_report = state.get("judge_report", {})
    unresolved = judge_report.get("unresolved_issues", [])

    await _notify({"type": "phase_change", "phase": "user_decision"})

    if state.get("enable_interrupt"):
        user_input = interrupt({
            "type": "resolution_decision",
            "unresolved_issues": unresolved,
            "retry_count": state.get("retry_count", 0),
            "options": [
                {"action": "accept", "label": "接受当前结果"},
                {"action": "retry_with_context", "label": "补充上下文后重试"},
                {"action": "stop", "label": "停止，手动修复"},
            ],
        })

        if user_input and isinstance(user_input, dict):
            action = user_input.get("action", "accept")

            if action == "retry_with_context":
                extra = user_input.get("context", "")
                return {
                    "extra_context": extra,
                    "user_decision": "auto_retry",
                    "retry_count": state.get("retry_count", 0),
                }

            if action == "stop":
                return {"user_decision": "user_stopped"}

    return {"user_decision": "user_accepted"}


def _user_decision_edge(state: DebateState) -> str:
    decision = state.get("user_decision", "user_accepted")
    if decision == "auto_retry":
        return "focused_retry"
    return "done"


# ─── Graph builder ──────────────────────────────────────────────────────────

_compiled_graph = None


def build_debate_graph():
    graph = StateGraph(DebateState)

    graph.add_node("plan", plan_node)
    graph.add_node("coder", coder_node)
    graph.add_node("security", security_node)
    graph.add_node("performance", performance_node)
    graph.add_node("correctness", correctness_node)
    graph.add_node("cross_review", cross_review_node)
    graph.add_node("arbitration", arbitration_node)
    graph.add_node("final_fix", final_fix_node)
    graph.add_node("judge", judge_node)
    graph.add_node("resolution_check", resolution_check_node)
    graph.add_node("focused_retry", focused_retry_node)
    graph.add_node("user_decision", user_decision_node)

    graph.set_entry_point("plan")

    def _plan_edge(state: DebateState) -> str:
        if state.get("plan_action") == "chat":
            return "plan"
        return "coder"

    graph.add_conditional_edges("plan", _plan_edge, {"plan": "plan", "coder": "coder"})

    graph.add_edge("coder", "security")
    graph.add_edge("coder", "performance")
    graph.add_edge("coder", "correctness")

    graph.add_edge("security", "cross_review")
    graph.add_edge("performance", "cross_review")
    graph.add_edge("correctness", "cross_review")

    graph.add_conditional_edges(
        "cross_review",
        check_consensus_edge,
        {
            "continue": "coder",
            "converged": "judge",
            "budget_exceeded": "arbitration",
        },
    )

    graph.add_conditional_edges(
        "arbitration",
        _arbitration_edge,
        {
            "deliver": "judge",
            "fix": "final_fix",
        },
    )

    graph.add_edge("final_fix", "judge")

    # Resolution loop: judge → resolution_check → (retry → judge | user_decision | done)
    graph.add_edge("judge", "resolution_check")

    graph.add_conditional_edges(
        "resolution_check",
        _resolution_check_edge,
        {
            "done": END,
            "focused_retry": "focused_retry",
            "user_decision": "user_decision",
        },
    )

    graph.add_edge("focused_retry", "judge")

    graph.add_conditional_edges(
        "user_decision",
        _user_decision_edge,
        {
            "focused_retry": "focused_retry",
            "done": END,
        },
    )

    return graph


_uncompiled_graph = None


def _get_uncompiled_graph():
    global _uncompiled_graph
    if _uncompiled_graph is None:
        _uncompiled_graph = build_debate_graph()
    return _uncompiled_graph


# ─── Full pipeline: pre-processing → graph → post-processing ───────────────

async def run_debate_with_graph(
    requirement: str,
    language: str = "python",
    framework: str | None = None,
    config: DebateConfig | None = None,
    api_key: str | None = None,
    on_progress: callable = None,
    interrupt_handler: callable = None,
) -> DebateResult:
    """Run a full debate through LangGraph with Memory/TestRunner/ComplexityRouter."""
    _progress_callback.set(on_progress)

    config = config or DebateConfig()
    start_time = time.monotonic()

    await _notify({"type": "status", "content": "正在理解需求..."})

    # --- Pre-processing: requirement parsing ---
    parsed_req = await parse_requirement(requirement, language, framework)

    complexity = route_complexity(requirement, parsed_req or {})
    # ComplexityRouter 仅用于前端展示复杂度标签，不覆盖 config。
    # 所有任务统一使用调用方传入的 config（默认：三路 Attacker、5 轮、不跳过交叉审阅）。

    # --- Memory retrieval ---
    from app.db.redis import get_redis
    attack_kb = AttackKnowledgeBase()
    user_prefs = UserPreferenceStore(redis_client=get_redis())
    fix_patterns = FixPatternStore()

    experience_prompt = ""
    experiences = await attack_kb.retrieve_relevant(requirement)
    if experiences:
        experience_prompt = attack_kb.build_experience_prompt(experiences)

    preference_prompt = ""
    if api_key:
        prefs = await user_prefs.get_preferences(api_key)
        if prefs:
            preference_prompt = user_prefs.build_preference_prompt(prefs)

    # --- Notify frontend: analysis complete ---
    await _notify({"type": "phase_change", "phase": "analysis"})
    await _notify({
        "type": "analysis_complete",
        "parsed_requirement": parsed_req,
        "complexity": complexity.value,
        "experiences": [
            {
                "content": exp.get("content", ""),
                "category": exp.get("category", "unknown"),
                "severity": exp.get("severity", "medium"),
                "session_id": exp.get("session_id"),
                "similarity": exp.get("similarity", 0),
            }
            for exp in experiences
        ] if experiences else [],
    })

    # --- Build initial graph state ---
    # Attackers not in config.attackers get skip-listed so graph nodes skip them
    all_attackers = {"security", "performance", "correctness"}
    skip_list = sorted(all_attackers - set(config.attackers))

    initial_state: DebateState = {
        "requirement": requirement,
        "language": language,
        "framework": framework or "",
        "current_code": "",
        "round": 0,
        "max_rounds": config.max_rounds,
        "messages": [],
        "consensus": {},
        "skip_list": skip_list,
        "extra_context": "",
        "experience_context": "",
        "preference_context": "",
        "parsed_requirement": parsed_req or {},
        "converged": False,
        "budget_spent": 0,
        "budget_total": config.max_tokens,
        "budget_by_agent": {},
        "budget_by_phase": {},
        "budget_cache_stats": {"read": 0, "creation": 0},
        "round_summaries": {},
        "judge_report": {},
        "arbitration_result": {},
        "must_fix_items": [],
        "convergence_reason": "",
        "selected_plan": "",
        "plan_content": "",
        "plan_round": 0,
        "plan_action": "",
        "config": {
            "max_rounds": config.max_rounds,
            "attackers": config.attackers,
            "model": config.model,
            "max_tokens": config.max_tokens,
            "skip_cross_review": config.skip_cross_review,
        },
        "enable_interrupt": interrupt_handler is not None,
        "retry_count": 0,
        "user_decision": "",
    }

    # Inject Memory context into separate state fields so _build_context
    # restores them into the correct DebateContext attributes (experience_context,
    # preference_context) that agents read from their get_system_prompt().
    if experience_prompt:
        initial_state["experience_context"] = experience_prompt
    if preference_prompt:
        initial_state["preference_context"] = preference_prompt

    # --- Run the LangGraph graph ---
    mysql_url = (
        f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    )
    async with AIOMySQLSaver.from_conn_string(mysql_url) as checkpointer:
        await checkpointer.setup()
        graph = _get_uncompiled_graph()
        compiled = graph.compile(checkpointer=checkpointer)
        thread_id = str(uuid.uuid4())
        graph_config = {"configurable": {"thread_id": thread_id}}
        # Interrupt-aware execution loop (LangGraph 1.x compatible).
        # In LangGraph >=1.0, ainvoke() returns normally at interrupt
        # points instead of raising GraphInterrupt. Detect pending
        # interrupts via get_state().next.
        invoke_input = initial_state
        final_state = None
        max_interrupts = 20

        for _interrupt_round in range(max_interrupts):
            _progress_callback.set(on_progress)
            final_state = await compiled.ainvoke(invoke_input, graph_config)
            snapshot = await compiled.aget_state(graph_config)
            if not snapshot.next:
                break
            interrupt_payload = {}
            if snapshot.tasks:
                for task in snapshot.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_payload = task.interrupts[0].value
                        break
            if interrupt_handler:
                user_response = await interrupt_handler(interrupt_payload)
            else:
                user_response = None
            invoke_input = Command(resume=user_response)

        # Always use aget_state for the complete merged state, not ainvoke's return value.
        # ainvoke may return partial state in interrupt-based execution.
        snapshot = await compiled.aget_state(graph_config)
        final_state = snapshot.values if hasattr(snapshot, "values") else (final_state or {})

    # --- Post-processing: TestRunner ---
    final_code = final_state.get("current_code", "")
    verify_summary = None
    if final_code:
        try:
            test_runner = TestRunner()
            ctx_for_test = DebateContext(requirement, config)
            for msg_dict in final_state.get("messages", []):
                ctx_for_test.messages.append(
                    DebateMessage(
                        agent=msg_dict["agent"],
                        content=msg_dict["content"],
                        round=msg_dict.get("round", 0),
                        structured=msg_dict.get("structured"),
                    )
                )
            verify_result = await test_runner.verify(
                final_code, requirement,
                llm_client=None,
                debate_context=ctx_for_test,
                language=language,
            )
            verify_summary = {
                "passed": verify_result.passed,
                "reason": verify_result.reason,
                "tests_passed": verify_result.tests_passed,
                "tests_failed": verify_result.tests_failed,
                "test_sources": verify_result.test_sources,
            }
            await _notify({"type": "test_result", **verify_summary})
            if not verify_result.passed:
                logger.info("graph_test_verification_failed stderr=%s", verify_result.stderr[:200])
        except Exception as e:
            logger.warning("graph_test_runner_error error=%s", e)

    # --- Post-processing: Memory write-back ---
    # Only store findings that Coder explicitly accepted (accept_and_fix).
    # Rebutted findings must NOT enter the knowledge base.
    accepted_refs: set[str] = set()
    for msg in final_state.get("messages", []):
        if msg["agent"] == "coder":
            structured = msg.get("structured")
            if structured and isinstance(structured, dict):
                for resp in structured.get("responses", []):
                    if resp.get("action") == "accept_and_fix":
                        accepted_refs.add(resp.get("finding_ref", ""))

    accepted_findings = []
    for msg in final_state.get("messages", []):
        if msg["agent"] in ("security", "performance", "correctness"):
            structured = msg.get("structured")
            if structured and isinstance(structured, dict):
                for f in structured.get("findings", []):
                    if not isinstance(f, dict):
                        continue
                    finding_key = f.get("category", "") or f.get("description", "")
                    ref_match = any(
                        finding_key.lower() in ref.lower() or ref.lower() in finding_key.lower()
                        for ref in accepted_refs if ref
                    )
                    if ref_match or (not accepted_refs and f.get("severity") in ("critical", "high")):
                        accepted_findings.append({
                            **f,
                            "was_accepted": True,
                            "tool_verified": f.get("tool_verified", False),
                            "attacker": msg["agent"],
                        })
    if accepted_findings:
        await attack_kb.store_findings(requirement, language, accepted_findings)

    for msg in final_state.get("messages", []):
        if msg["agent"] == "coder" and msg.get("code") and msg.get("structured"):
            for resp in msg["structured"].get("responses", []):
                if resp.get("action") == "accept_and_fix":
                    await fix_patterns.store_fix(
                        finding_description=resp.get("explanation", ""),
                        category=resp.get("finding_ref", "unknown"),
                        severity="medium",
                        fix_code=msg["code"],
                    )

    if api_key:
        await user_prefs.update_from_request(api_key, {"language": language})

    # --- Notify convergence ---
    final_round = final_state.get("round", 0)
    is_converged = final_state.get("converged", False)
    if is_converged:
        await _notify({"type": "converged", "round": final_round, "reason": "各方达成共识"})

    # --- Metrics ---
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    record_debate_complete(
        language=language,
        complexity=complexity.value,
        rounds=final_round,
        converged=is_converged,
        duration_s=elapsed_ms / 1000,
    )

    # --- Build DebateResult ---
    judge_report = final_state.get("judge_report", {})
    logger.info("final_state_keys=%s judge_report_keys=%s judge_report_star=%s",
                list(final_state.keys()) if isinstance(final_state, dict) else type(final_state).__name__,
                list(judge_report.keys()) if isinstance(judge_report, dict) else type(judge_report).__name__,
                judge_report.get("star_rating") if isinstance(judge_report, dict) else "N/A")
    budget_spent = final_state.get("budget_spent", 0)
    sonnet_rate = (3.0 + 15.0) / 2 / 1_000_000
    cost_usd = round(budget_spent * sonnet_rate, 4)

    transcript_rounds: dict[int, list[dict]] = {}
    for msg in final_state.get("messages", []):
        r = msg.get("round", 0)
        entry: dict = {
            "agent": msg["agent"],
            "content": msg["content"],
            "code": msg.get("code"),
        }
        if msg.get("structured"):
            entry["structured"] = msg["structured"]
        transcript_rounds.setdefault(r, []).append(entry)
    transcript = [
        {"round": r, "messages": msgs}
        for r, msgs in sorted(transcript_rounds.items())
    ]

    result = DebateResult(
        code=final_code,
        language=language,
        confidence=judge_report.get("confidence", 0.0),
        debate={
            "total_rounds": final_round,
            "converged": is_converged,
            "consensus_reason": final_state.get(
                "convergence_reason",
                "各方达成共识" if is_converged else "达到最大轮次或预算上限",
            ),
            "transcript": transcript,
        },
        summary=DebateSummary(
            total_issues_raised=judge_report.get("total_issues_raised", 0),
            accepted_and_fixed=judge_report.get("accepted_and_fixed", 0),
            rejected_by_coder=judge_report.get("rejected_by_coder", 0),
            suggestions_noted=judge_report.get("suggestions_noted", 0),
            key_improvements=judge_report.get("key_improvements", []),
        ),
        risk_assessment=RiskAssessment(
            security=judge_report.get("risk_security", "unknown"),
            performance=judge_report.get("risk_performance", "unknown"),
            correctness=judge_report.get("risk_correctness", "unknown"),
        ),
        metrics=DebateMetrics(
            total_rounds=final_round,
            total_tokens=budget_spent,
            total_latency_ms=elapsed_ms,
            cost_usd=cost_usd,
        ),
        quality_report=QualityReport(
            star_rating=judge_report.get("star_rating", 0),
            star_comment=judge_report.get("star_comment", ""),
            resolved_issues=judge_report.get("resolved_issues", []),
            unresolved_issues=judge_report.get("unresolved_issues", []),
            score_security=judge_report.get("score_security", 0),
            score_performance=judge_report.get("score_performance", 0),
            score_correctness=judge_report.get("score_correctness", 0),
            usage_advice=judge_report.get("usage_advice", ""),
        ),
        converged=is_converged,
        convergence_reason=final_state.get(
            "convergence_reason",
            "各方达成共识" if is_converged else "达到最大轮次或预算上限",
        ),
        metadata={
            "engine": "langgraph",
            "thread_id": thread_id,
            "arbitration": final_state.get("arbitration_result") or None,
            "requires_human_review": _needs_human_review(final_state),
            "process_transparency": {
                "complexity": complexity.value,
                "memory_reads": len(experiences) if experiences else 0,
                "memory_writes_findings": len(accepted_findings),
                "consensus_status": final_state.get("consensus", {}),
                "test_verification": verify_summary,
            },
        },
    )

    await _notify({"type": "done"})
    _progress_callback.set(None)
    return result
