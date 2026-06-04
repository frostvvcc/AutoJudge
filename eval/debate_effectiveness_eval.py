"""
Debate effectiveness evaluation: extract 5 key metrics from completed
debate sessions stored in MySQL.

Metrics:
  1. Finding Precision: accept_and_fix / total findings (ideal: 50-70%)
  2. Rebuttal Success Rate: rebuttals where attacker later satisfied / total rebuttals (ideal: 60-80%)
  3. Fix Effective Rate: confirmed-fixed in next round / accept_and_fix (ideal: >90%)
  4. Convergence Rate: sessions that converged naturally / total sessions
  5. Avg Rounds: average rounds per session (ideal: 2-3)

Usage:
    python -m eval.debate_effectiveness_eval
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session
from app.db.models import DebateSession, DebateMessage

logger = logging.getLogger(__name__)


async def _load_sessions(session: AsyncSession) -> list[DebateSession]:
    """Load all completed debate sessions with their messages."""
    stmt = (
        select(DebateSession)
        .where(DebateSession.status == "completed")
        .order_by(DebateSession.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _extract_findings(messages: list[DebateMessage]) -> list[dict]:
    """Extract all findings from attacker messages' structured_json."""
    findings = []
    for msg in messages:
        if msg.agent not in ("security", "performance", "correctness"):
            continue
        structured = msg.structured_json or {}
        for finding in structured.get("findings", []):
            findings.append({
                "attacker": msg.agent,
                "round": msg.round,
                "description": finding.get("description", ""),
                "severity": finding.get("severity", "unknown"),
                "category": finding.get("category", msg.agent),
                **finding,
            })
    return findings


def _extract_coder_responses(messages: list[DebateMessage]) -> list[dict]:
    """Extract coder responses from structured_json."""
    responses = []
    for msg in messages:
        if msg.agent != "coder":
            continue
        structured = msg.structured_json or {}
        for resp in structured.get("responses", []):
            responses.append({
                "round": msg.round,
                "action": resp.get("action", ""),
                "finding_ref": resp.get("finding_ref", ""),
                "explanation": resp.get("explanation", ""),
            })
    return responses


def _count_accept_and_fix(coder_responses: list[dict]) -> int:
    """Count how many findings the coder accepted and fixed."""
    return sum(1 for r in coder_responses if r["action"] == "accept_and_fix")


def _count_rebuttals(coder_responses: list[dict]) -> int:
    """Count how many findings the coder rebutted."""
    return sum(1 for r in coder_responses if r["action"] == "rebuttal")


def _count_successful_rebuttals(
    coder_responses: list[dict],
    messages: list[DebateMessage],
) -> int:
    """
    Count rebuttals where the attacker later set stance=satisfied,
    meaning the rebuttal was convincing.
    """
    rebutted_refs = set()
    rebuttal_rounds: dict[str, int] = {}
    for resp in coder_responses:
        if resp["action"] == "rebuttal" and resp["finding_ref"]:
            rebutted_refs.add(resp["finding_ref"])
            rebuttal_rounds[resp["finding_ref"]] = resp["round"]

    if not rebutted_refs:
        return 0

    successful = 0
    for msg in messages:
        if msg.agent not in ("security", "performance", "correctness"):
            continue
        structured = msg.structured_json or {}
        stance = structured.get("stance", "")
        if stance == "satisfied":
            # Check if this attacker had a finding that was rebutted
            for finding in structured.get("findings", []):
                ref = finding.get("finding_ref", finding.get("description", ""))
                if ref in rebutted_refs and msg.round > rebuttal_rounds.get(ref, 0):
                    successful += 1
                    rebutted_refs.discard(ref)

    # Also count by attacker-level satisfaction after rebuttal round
    for msg in messages:
        if msg.agent not in ("security", "performance", "correctness"):
            continue
        structured = msg.structured_json or {}
        if structured.get("stance") == "satisfied":
            # If this attacker had any rebutted findings and is now satisfied
            for ref, rnd in list(rebuttal_rounds.items()):
                if msg.round > rnd and ref in rebutted_refs:
                    successful += 1
                    rebutted_refs.discard(ref)

    return successful


def _count_fix_confirmed_next_round(
    coder_responses: list[dict],
    messages: list[DebateMessage],
) -> int:
    """
    Count accept_and_fix responses where the fix was confirmed in the next round
    (attacker did not re-raise the same issue).
    """
    fixed_items: list[dict] = [
        r for r in coder_responses if r["action"] == "accept_and_fix"
    ]
    if not fixed_items:
        return 0

    # Group attacker findings by round
    findings_by_round: dict[int, set[str]] = {}
    for msg in messages:
        if msg.agent not in ("security", "performance", "correctness"):
            continue
        structured = msg.structured_json or {}
        for finding in structured.get("findings", []):
            desc = finding.get("description", "")
            findings_by_round.setdefault(msg.round, set()).add(desc.lower())

    confirmed = 0
    for fix in fixed_items:
        fix_round = fix["round"]
        next_round = fix_round + 1
        next_findings = findings_by_round.get(next_round, set())
        ref = fix.get("finding_ref", "").lower()
        explanation = fix.get("explanation", "").lower()

        # If the fixed issue was NOT re-raised in the next round, it's confirmed
        re_raised = False
        for next_desc in next_findings:
            if ref and ref in next_desc:
                re_raised = True
                break
            if explanation and len(explanation) > 10 and explanation[:20] in next_desc:
                re_raised = True
                break

        if not re_raised:
            confirmed += 1

    return confirmed


async def _evaluate_session(
    db_session: DebateSession,
) -> dict:
    """Evaluate a single debate session and return per-session metrics."""
    messages = db_session.messages or []
    if not messages:
        return {
            "session_id": db_session.sid,
            "status": "no_messages",
        }

    findings = _extract_findings(messages)
    coder_responses = _extract_coder_responses(messages)
    total_findings = len(findings)
    accept_fix_count = _count_accept_and_fix(coder_responses)
    rebuttal_count = _count_rebuttals(coder_responses)
    successful_rebuttals = _count_successful_rebuttals(coder_responses, messages)
    fix_confirmed = _count_fix_confirmed_next_round(coder_responses, messages)

    finding_precision = (
        round(accept_fix_count / total_findings, 4)
        if total_findings > 0
        else 0.0
    )
    rebuttal_success_rate = (
        round(successful_rebuttals / rebuttal_count, 4)
        if rebuttal_count > 0
        else 0.0
    )
    fix_effective_rate = (
        round(fix_confirmed / accept_fix_count, 4)
        if accept_fix_count > 0
        else 0.0
    )

    return {
        "session_id": db_session.sid,
        "task": db_session.task[:80] if db_session.task else "",
        "total_rounds": db_session.total_rounds,
        "converged": db_session.converged,
        "convergence_reason": db_session.convergence_reason or "",
        "total_findings": total_findings,
        "accept_and_fix_count": accept_fix_count,
        "rebuttal_count": rebuttal_count,
        "successful_rebuttals": successful_rebuttals,
        "fix_confirmed_next_round": fix_confirmed,
        "finding_precision": finding_precision,
        "rebuttal_success_rate": rebuttal_success_rate,
        "fix_effective_rate": fix_effective_rate,
    }


async def run_debate_effectiveness_eval() -> dict:
    """
    Run debate effectiveness evaluation across all completed sessions.

    Returns a JSON report with 5 aggregate metrics and per-session breakdown.
    """
    async with async_session() as session:
        db_sessions = await _load_sessions(session)

    if not db_sessions:
        return {
            "error": "No completed debate sessions found in database.",
            "metrics": {},
            "sessions": [],
        }

    logger.info("Evaluating %d completed debate sessions", len(db_sessions))

    session_results = []
    for db_sess in db_sessions:
        result = await _evaluate_session(db_sess)
        session_results.append(result)

    # Aggregate metrics
    valid = [s for s in session_results if s.get("status") != "no_messages"]
    total_sessions = len(valid)

    if total_sessions == 0:
        return {
            "error": "All sessions had no messages.",
            "metrics": {},
            "sessions": session_results,
        }

    total_findings_all = sum(s["total_findings"] for s in valid)
    total_accept_fix = sum(s["accept_and_fix_count"] for s in valid)
    total_rebuttals = sum(s["rebuttal_count"] for s in valid)
    total_successful_rebuttals = sum(s["successful_rebuttals"] for s in valid)
    total_fix_confirmed = sum(s["fix_confirmed_next_round"] for s in valid)
    converged_count = sum(1 for s in valid if s["converged"])
    total_rounds_sum = sum(s["total_rounds"] for s in valid)

    metrics = {
        "finding_precision": {
            "value": round(total_accept_fix / max(total_findings_all, 1), 4),
            "ideal_range": "0.50-0.70",
            "description": "accept_and_fix count / total findings",
            "numerator": total_accept_fix,
            "denominator": total_findings_all,
        },
        "rebuttal_success_rate": {
            "value": round(
                total_successful_rebuttals / max(total_rebuttals, 1), 4
            ),
            "ideal_range": "0.60-0.80",
            "description": "rebuttals where attacker later satisfied / total rebuttals",
            "numerator": total_successful_rebuttals,
            "denominator": total_rebuttals,
        },
        "fix_effective_rate": {
            "value": round(
                total_fix_confirmed / max(total_accept_fix, 1), 4
            ),
            "ideal_range": ">0.90",
            "description": "confirmed-fixed in next round / accept_and_fix count",
            "numerator": total_fix_confirmed,
            "denominator": total_accept_fix,
        },
        "convergence_rate": {
            "value": round(converged_count / total_sessions, 4),
            "description": "sessions that converged naturally / total sessions",
            "numerator": converged_count,
            "denominator": total_sessions,
        },
        "avg_rounds": {
            "value": round(total_rounds_sum / total_sessions, 2),
            "ideal_range": "2-3",
            "description": "average rounds per session",
        },
    }

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_sessions": total_sessions,
        "metrics": metrics,
        "sessions": session_results,
    }


async def main():
    """Entry point for running the evaluation."""
    report = await run_debate_effectiveness_eval()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main())
