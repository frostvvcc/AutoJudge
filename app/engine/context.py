from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DebateMessage:
    agent: str
    content: str
    round: int
    code: str | None = None
    structured: dict | None = None


@dataclass
class DebateConfig:
    mode: str = "pro"
    max_rounds: int = 5
    attackers: list[str] = field(
        default_factory=lambda: ["security", "performance", "correctness"]
    )
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 500_000
    skip_cross_review: bool = False


class DebateContext:
    """
    All agents share a single debate context.
    Each agent sees the full conversation history when speaking.
    """

    def __init__(self, requirement: str, config: DebateConfig | None = None):
        self.messages: list[DebateMessage] = []
        self.requirement = requirement
        self.current_code: str = ""
        self.code_versions: list[str] = []
        self.round: int = 0
        self.round_summaries: dict[int, str] = {}
        self.config = config or DebateConfig()
        self.skip_list: list[str] = []
        self.extra_context: str | None = None
        self.experience_context: str = ""
        self.preference_context: str = ""
        self.parsed_requirement: dict | None = None

    def add_message(
        self,
        agent: str,
        content: str,
        code: str | None = None,
        structured: dict | None = None,
    ):
        self.messages.append(
            DebateMessage(
                agent=agent,
                content=content,
                round=self.round,
                code=code,
                structured=structured,
            )
        )
        if code:
            self.current_code = code
            self.code_versions.append(code)

    def set_requirement_context(self, parsed: dict):
        self.parsed_requirement = parsed

    def set_experience_context(self, prompt: str):
        self.experience_context = prompt

    def set_preference_context(self, prompt: str):
        self.preference_context = prompt

    def get_context_for_agent(self, agent: str) -> list[dict]:
        """
        Layer 2: Agent-Specific View — 每个 Agent 只看到跟自己相关的信息。

        三层上下文架构：
          Layer 1: Shared State (DebateState TypedDict) — 全局可读，不灌 prompt
          Layer 2: Agent-Specific View — 本方法，按角色裁剪
          Layer 3: Structured Summary Injection — cross_review_node 负责

        裁剪规则：
          攻击者 → 自己的历史 + Coder 对自己的回应（不看其他攻击者）
          Coder  → 最新一轮所有攻击者的发言（不看旧版代码/方案讨论）
          Judge  → 全局视图（需要总结整个辩论过程）
        """
        if agent in ("security", "performance", "correctness"):
            return self._build_attacker_view(agent)
        elif agent == "coder":
            return self._build_coder_view()
        elif agent in ("judge", "arbitrator"):
            return self._build_judge_view()
        else:
            return self._build_default_view(agent)

    def _build_attacker_view(self, agent: str) -> list[dict]:
        """攻击者只看：自己之前的发言 + Coder 对自己的回应。"""
        messages = []
        recent_cutoff = max(0, self.round - 2)

        if self.round > 2 and self.round_summaries:
            own_summary = self._filter_summary_for(agent)
            if own_summary:
                messages.append(
                    {"role": "user", "content": f"早期轮次摘要：\n{own_summary}"}
                )
                messages.append(
                    {"role": "assistant", "content": "已了解历史背景，继续审查。"}
                )

        for msg in self.messages:
            if msg.round < recent_cutoff:
                continue

            if msg.agent == agent:
                messages.append({"role": "assistant", "content": msg.content})
            elif msg.agent == "coder":
                relevant = self._extract_coder_response_for(msg, agent)
                if relevant:
                    messages.append({"role": "user", "content": f"[CODER] {relevant}"})

        if not messages or messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "请开始/继续你的审查。"})

        return messages

    def _build_coder_view(self) -> list[dict]:
        """Coder 只看：最新一轮攻击者的发言 + 自己之前的回应。"""
        messages = []
        recent_cutoff = max(0, self.round - 2)

        if self.round > 2 and self.round_summaries:
            summary = "\n".join(
                f"Round {r}: {s}" for r, s in self.round_summaries.items()
            )
            messages.append(
                {"role": "user", "content": f"早期轮次摘要：\n{summary}"}
            )
            messages.append(
                {"role": "assistant", "content": "已了解，继续。"}
            )

        for msg in self.messages:
            if msg.round < recent_cutoff:
                continue
            if msg.agent == "coder":
                messages.append({"role": "assistant", "content": msg.content})
            elif msg.agent in ("security", "performance", "correctness"):
                content_parts = [f"[{msg.agent.upper()}] {msg.content}"]
                if msg.structured and isinstance(msg.structured, dict):
                    findings = msg.structured.get("findings", [])
                    if findings:
                        content_parts.append("\n结构化 findings（请用 finding_ref 逐条引用回应）：")
                        for fi, f in enumerate(findings):
                            ref = f"{msg.agent.upper()}-{str(fi + 1).zfill(3)}"
                            sev = f.get("severity", "?").upper() if isinstance(f, dict) else "?"
                            cat = f.get("category", "?") if isinstance(f, dict) else "?"
                            desc = f.get("description", "") if isinstance(f, dict) else str(f)
                            content_parts.append(f"  [{ref}] {sev} {cat}: {desc}")
                messages.append(
                    {"role": "user", "content": "\n".join(content_parts)}
                )

        if not messages or messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "请回应攻击者的意见。"})

        return messages

    def _build_judge_view(self) -> list[dict]:
        """Judge/Arbitrator 需要全局视图（总结整个辩论）。"""
        messages = []
        recent_cutoff = max(0, self.round - 2)

        if self.round > 2 and self.round_summaries:
            summary = "\n".join(
                f"Round {r}: {s}" for r, s in self.round_summaries.items()
            )
            messages.append(
                {"role": "user", "content": f"早期轮次摘要：\n{summary}"}
            )
            messages.append(
                {"role": "assistant", "content": "已了解历史背景。"}
            )

        rounds: dict[int, list[DebateMessage]] = {}
        for msg in self.messages:
            if msg.round >= recent_cutoff:
                rounds.setdefault(msg.round, []).append(msg)

        for round_num in sorted(rounds.keys()):
            combined = "\n\n".join(
                f"[{m.agent.upper()}] {m.content}" for m in rounds[round_num]
            )
            if messages and messages[-1]["role"] == "user":
                messages.append({"role": "assistant", "content": "继续审阅下一轮。"})
            messages.append({"role": "user", "content": combined})

        if not messages:
            messages.append({"role": "user", "content": "请开始评判。"})

        return messages

    def _build_default_view(self, agent: str) -> list[dict]:
        """兜底：planner/compressor 等轻量 Agent。"""
        messages = []
        for msg in self.messages:
            if msg.agent == agent:
                messages.append({"role": "assistant", "content": msg.content})
            else:
                messages.append(
                    {"role": "user", "content": f"[{msg.agent.upper()}] {msg.content}"}
                )
        if not messages:
            messages.append({"role": "user", "content": "请开始你的工作。"})
        return messages

    def _extract_coder_response_for(self, msg: DebateMessage, target_agent: str) -> str | None:
        """从 Coder 的回应中提取针对特定攻击者的部分。"""
        if not msg.structured or not isinstance(msg.structured, dict):
            return msg.content

        responses = msg.structured.get("responses", [])
        relevant_parts = []
        for resp in responses:
            ref = resp.get("finding_ref", "").lower()
            if target_agent.lower() in ref:
                action = resp.get("action", "")
                explanation = resp.get("explanation", "")
                relevant_parts.append(f"[{action}] {explanation}")

        if relevant_parts:
            return "\n".join(relevant_parts)
        return msg.content

    def _filter_summary_for(self, agent: str) -> str:
        """从早期轮次摘要中过滤与特定攻击者相关的内容。"""
        parts = []
        for r, s in sorted(self.round_summaries.items()):
            if agent in s.lower() or "coder" in s.lower():
                parts.append(f"Round {r}: {s}")
        return "\n".join(parts)

    async def compress_early_rounds(self, llm_client=None):
        """Compress the oldest full round into a summary via unified call_agent."""
        if self.round <= 2:
            return

        oldest_round = self.round - 2
        if oldest_round in self.round_summaries:
            return

        round_msgs = [m for m in self.messages if m.round == oldest_round]
        if not round_msgs:
            return

        from app.llm.client import call_agent

        text = "\n".join(f"[{m.agent}] {m.content}" for m in round_msgs)

        try:
            response = await call_agent(
                agent="compressor",
                system_prompt="你是摘要助手。用 2-3 句话总结对话的关键信息。只输出摘要文本，不要 JSON。",
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "总结这轮对话（发现了什么问题、修复了什么、有什么争议）：\n\n"
                            f"{text}"
                        ),
                    }
                ],
                max_tokens=200,
            )
            self.round_summaries[oldest_round] = response.content
        except Exception:
            pass

    def get_transcript(self) -> list[dict]:
        """Export full conversation as structured transcript."""
        rounds: dict[int, list[dict]] = {}
        for msg in self.messages:
            rounds.setdefault(msg.round, []).append(
                {
                    "agent": msg.agent,
                    "content": msg.content,
                    "code": msg.code,
                }
            )
        return [
            {"round": r, "messages": msgs}
            for r, msgs in sorted(rounds.items())
        ]
