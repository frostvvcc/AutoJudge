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
    max_rounds: int = 5
    attackers: list[str] = field(
        default_factory=lambda: ["security", "performance", "correctness"]
    )
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 100_000
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
        Build the message list for a specific agent.
        Uses sliding window + early-round summaries to prevent context explosion.

        Key design: all other agents' messages in a round are merged into one
        user message to satisfy Claude API's strict user/assistant alternation.
        """
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
                {"role": "assistant", "content": "已了解历史对话背景，继续。"}
            )

        rounds: dict[int, list[DebateMessage]] = {}
        for msg in self.messages:
            if msg.round > recent_cutoff:
                rounds.setdefault(msg.round, []).append(msg)

        for round_num in sorted(rounds.keys()):
            round_msgs = rounds[round_num]
            my_msgs = [m for m in round_msgs if m.agent == agent]
            other_msgs = [m for m in round_msgs if m.agent != agent]

            if other_msgs:
                combined = "\n\n".join(
                    f"[{m.agent.upper()}] {m.content}" for m in other_msgs
                )
                messages.append({"role": "user", "content": combined})

            if my_msgs:
                combined = "\n\n".join(m.content for m in my_msgs)
                messages.append({"role": "assistant", "content": combined})

        if messages and messages[-1]["role"] == "assistant":
            messages.append(
                {"role": "user", "content": "请继续你的审查/回应。"}
            )

        if not messages:
            messages.append(
                {"role": "user", "content": "请开始你的工作。"}
            )

        return messages

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
