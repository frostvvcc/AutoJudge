from __future__ import annotations

from app.engine.context import DebateMessage

REQUIRED_ATTACKERS = {"security", "performance", "correctness"}


class ConsensusDetector:
    """
    Convergence requires ALL non-error attackers to report stance=satisfied.
    Error agents (stance='error') are excluded from consensus evaluation —
    they don't block convergence.
    """

    def check_consensus(
        self,
        round_messages: list[DebateMessage],
        active_attackers: set[str] | None = None,
    ) -> dict:
        required = active_attackers or REQUIRED_ATTACKERS
        attacker_status: dict[str, bool] = {}

        errored: set[str] = set()
        for msg in round_messages:
            if msg.agent in required:
                if msg.structured and msg.structured.get("stance") == "error":
                    errored.add(msg.agent)

        effective_required = required - errored

        for msg in round_messages:
            if msg.agent in effective_required:
                if msg.structured and "stance" in msg.structured:
                    attacker_status[msg.agent] = (
                        msg.structured["stance"] == "satisfied"
                    )

        if not attacker_status and not errored:
            return {"converged": False, "status": {}}

        if not attacker_status and errored:
            return {"converged": False, "status": {a: False for a in errored}}

        for attacker in effective_required:
            if attacker not in attacker_status:
                attacker_status[attacker] = False

        for a in errored:
            attacker_status[a] = False

        all_clear = all(
            attacker_status[a] for a in effective_required if a in attacker_status
        ) if effective_required else False

        return {
            "converged": all_clear,
            "status": attacker_status,
        }
