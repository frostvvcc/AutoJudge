from __future__ import annotations

from app.engine.context import DebateMessage


class ConsensusDetector:
    """
    Convergence is based solely on Structured Output stance fields.
    No keyword matching — natural language is too ambiguous.
    """

    def check_consensus(self, round_messages: list[DebateMessage]) -> dict:
        attacker_status: dict[str, bool] = {}

        for msg in round_messages:
            if msg.agent in ("security", "performance", "correctness"):
                if msg.structured and "stance" in msg.structured:
                    attacker_status[msg.agent] = (
                        msg.structured["stance"] == "satisfied"
                    )

        if not attacker_status:
            return {"converged": False, "status": {}}

        all_clear = all(attacker_status.values())
        return {
            "converged": all_clear,
            "status": attacker_status,
        }
