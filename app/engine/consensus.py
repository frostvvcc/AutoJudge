from __future__ import annotations

from app.engine.context import DebateMessage

REQUIRED_ATTACKERS = {"security", "performance", "correctness"}


class ConsensusDetector:
    """
    Convergence requires ALL configured attackers to report stance=satisfied.
    Missing attackers are treated as NOT satisfied (fail-closed).
    """

    def check_consensus(
        self,
        round_messages: list[DebateMessage],
        active_attackers: set[str] | None = None,
    ) -> dict:
        required = active_attackers or REQUIRED_ATTACKERS
        attacker_status: dict[str, bool] = {}

        for msg in round_messages:
            if msg.agent in required:
                if msg.structured and "stance" in msg.structured:
                    attacker_status[msg.agent] = (
                        msg.structured["stance"] == "satisfied"
                    )

        if not attacker_status:
            return {"converged": False, "status": {}}

        for attacker in required:
            if attacker not in attacker_status:
                attacker_status[attacker] = False

        all_clear = all(attacker_status.values())
        return {
            "converged": all_clear,
            "status": attacker_status,
        }
