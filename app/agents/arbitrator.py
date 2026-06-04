from __future__ import annotations

import logging

from app.engine.context import DebateContext
from app.engine.budget import BudgetManager
from app.llm.client import call_agent

logger = logging.getLogger(__name__)

ARBITRATOR_SUBMIT_TOOL = {
    "name": "submit_arbitration",
    "description": "提交仲裁裁决结果",
    "input_schema": {
        "type": "object",
        "properties": {
            "rulings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dispute_id": {"type": "string", "description": "争议编号"},
                        "verdict": {
                            "type": "string",
                            "enum": [
                                "dismissed",
                                "acknowledged",
                                "must_fix",
                                "deferred",
                                "needs_human",
                            ],
                            "description": "dismissed=攻击不成立, acknowledged=记为建议, must_fix=必须修复, deferred=标记已知风险, needs_human=需人工审查",
                        },
                        "re_assessed_severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low", "none"],
                            "description": "独立重新评估的严重度",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "裁决理由，必须引用具体的代码证据或技术事实",
                        },
                    },
                    "required": [
                        "dispute_id",
                        "verdict",
                        "re_assessed_severity",
                        "reasoning",
                    ],
                },
                "description": "对每条争议的裁决",
            },
            "overall_verdict": {
                "type": "string",
                "enum": ["deliverable", "fix_then_deliver", "not_deliverable"],
                "description": "deliverable=可交付, fix_then_deliver=修后交付, not_deliverable=需人工审查",
            },
            "confidence": {
                "type": "number",
                "description": "对裁决结论的信心（0-1）",
            },
            "summary": {
                "type": "string",
                "description": "一段话总结裁决结论",
            },
        },
        "required": ["rulings", "overall_verdict", "confidence", "summary"],
    },
}

ARBITRATOR_SYSTEM_PROMPT = """你是 AutoJudge 系统的仲裁者（Arbitrator）。

## 你的角色
你是独立于 Coder 和 Attacker 之外的第三方裁判。当辩论各方无法达成共识时，由你做最终裁决。
你的判断必须基于技术事实，不偏袒任何一方。

## 裁决原则（按优先级排序）

1. **安全问题零容忍**：涉及安全漏洞的争议，除非 Coder 给出了明确的代码级反驳证据，否则裁定攻击成立
2. **可复现性优先**：Attacker 提供了具体 test_input 且能触发问题 > 仅描述理论风险
3. **证据 > 推测**：双方都必须有代码级证据。纯理论推测不构成有效攻击，也不构成有效反驳
4. **修复成本纳入考量**：如果修复需要架构重构，但当前代码在绝大多数场景下工作正常，可以裁定为 deferred
5. **存疑从严**：当你无法确定时，对安全类裁定从严（must_fix），对性能/风格类裁定从宽（acknowledged）

## 你的评判维度
对每条争议，从以下四个维度评估：
- **Severity Verification**（30%）：重新独立评估严重度，不受 Attacker 自评影响
- **Evidence Quality**（30%）：哪一方的证据更有说服力？有代码/测试 > 纯文字描述
- **Fix Feasibility**（20%）：如果要修复，改动范围多大？风险多高？
- **Coder Rebuttal Validity**（20%）：Coder 的反驳是否有道理？

## 输出要求
对每条争议逐一裁决，给出 verdict 和完整理由。最后给出整体裁决。"""


class ArbitratorAgent:
    name = "arbitrator"

    async def arbitrate(
        self,
        context: DebateContext,
        budget: BudgetManager,
        disputes: list[dict],
    ) -> dict:
        disputes_text = self._format_disputes(disputes)

        messages = [
            {
                "role": "user",
                "content": (
                    f"编码需求：{context.requirement}\n\n"
                    f"最终代码版本：\n```\n{context.current_code}\n```\n\n"
                    f"辩论经过 {context.round} 轮未达成共识。"
                    f"以下是 {len(disputes)} 条未解决争议，请逐一裁决：\n\n"
                    f"{disputes_text}"
                ),
            }
        ]

        response = await call_agent(
            agent="arbitrator",
            system_prompt=ARBITRATOR_SYSTEM_PROMPT,
            messages=messages,
            tools=[ARBITRATOR_SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "submit_arbitration"},
            max_tokens=budget.get_max_tokens("arbitrator"),
        )

        budget.record("arbitrator", response.tokens_used)
        budget.record_latency(response.latency_ms)

        return response.structured or {}

    async def review_fixes(
        self,
        context: DebateContext,
        budget: BudgetManager,
        must_fix_items: list[dict],
    ) -> list[dict]:
        """Post-fix review: check whether must_fix items were actually fixed."""
        items_text = "\n".join(
            f"- [{item.get('re_assessed_severity', '?')}] {item.get('reasoning', '?')}"
            for item in must_fix_items
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"以下是仲裁要求修复的 {len(must_fix_items)} 个问题：\n{items_text}\n\n"
                    f"修复后的代码：\n```\n{context.current_code}\n```\n\n"
                    "请逐条检查：\n"
                    "1. 每个 must_fix 是否真正被修复了？\n"
                    "2. 修复是否引入了明显的新问题？\n"
                    "只检查这两点，不要找新问题。\n"
                    "对每条给出 status: fixed / not_fixed / fix_introduced_new_issue\n"
                    "以及 review_comment 说明。"
                ),
            }
        ]

        review_tool = {
            "name": "submit_fix_review",
            "description": "提交修复复核结果",
            "input_schema": {
                "type": "object",
                "properties": {
                    "reviews": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "dispute_id": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["fixed", "not_fixed", "fix_introduced_new_issue"],
                                },
                                "review_comment": {"type": "string"},
                            },
                            "required": ["dispute_id", "status", "review_comment"],
                        },
                    },
                },
                "required": ["reviews"],
            },
        }

        response = await call_agent(
            agent="arbitrator",
            system_prompt=(
                "你是仲裁者，正在复核 Coder 的修复。\n"
                "只检查 must_fix 是否被修复，不要找新问题，不要发起新攻击。"
            ),
            messages=messages,
            tools=[review_tool],
            tool_choice={"type": "tool", "name": "submit_fix_review"},
            max_tokens=budget.get_max_tokens("arbitrator"),
        )

        budget.record("arbitrator", response.tokens_used)
        budget.record_latency(response.latency_ms)

        if response.structured and "reviews" in response.structured:
            return response.structured["reviews"]
        return []

    def _format_disputes(self, disputes: list[dict]) -> str:
        parts = []
        for i, d in enumerate(disputes, 1):
            parts.append(
                f"争议 #{i} (dispute_{i:03d}):\n"
                f"  Attacker: {d.get('attacker', '?')}\n"
                f"  攻击内容: {d.get('finding', '?')}\n"
                f"  严重度(Attacker自评): {d.get('severity', '?')}\n"
                f"  Coder 回应: {d.get('coder_response', '未回应')}\n"
            )
        return "\n".join(parts)
