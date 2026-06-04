"""
Arbitration accuracy evaluation: three methods to evaluate
whether the Arbitrator (Judge) makes correct rulings on disputed findings.

Method 1 - Human Label Comparison:
    Compare Arbitrator rulings against human-annotated ground truth.

Method 2 - Code Verification:
    For disputes with test_input, run tests in Docker sandbox to verify.

Method 3 - LLM-as-Judge (placeholder):
    Feed dispute+evidence+ruling to a separate LLM for evaluation.
    Requires API key to run.

Usage:
    python -m eval.arbitration_eval
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session
from app.db.models import DebateSession, DebateMessage

logger = logging.getLogger(__name__)

HUMAN_LABELS_PATH = Path(__file__).parent / "human_labels" / "arbitration_labels.json"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _load_completed_sessions(session: AsyncSession) -> list[DebateSession]:
    """Load completed sessions with messages."""
    stmt = (
        select(DebateSession)
        .where(DebateSession.status == "completed")
        .order_by(DebateSession.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _extract_disputes(session_data: DebateSession) -> list[dict]:
    """
    Extract disputes from a debate session.

    A dispute occurs when a coder rebuts an attacker finding and the
    Judge (Arbitrator) later renders a verdict in the summary_json.
    """
    messages = session_data.messages or []
    disputes = []

    # Collect coder rebuttals
    rebuttals: dict[str, dict] = {}
    for msg in messages:
        if msg.agent != "coder":
            continue
        structured = msg.structured_json or {}
        for resp in structured.get("responses", []):
            if resp.get("action") == "rebuttal":
                ref = resp.get("finding_ref", resp.get("explanation", ""))
                rebuttals[ref] = {
                    "round": msg.round,
                    "explanation": resp.get("explanation", ""),
                    "evidence": resp.get("evidence", ""),
                }

    # Collect attacker findings that were rebutted
    for msg in messages:
        if msg.agent not in ("security", "performance", "correctness"):
            continue
        structured = msg.structured_json or {}
        for finding in structured.get("findings", []):
            desc = finding.get("description", "")
            ref = finding.get("finding_ref", desc)
            if ref in rebuttals or desc in rebuttals:
                rebuttal = rebuttals.get(ref) or rebuttals.get(desc, {})
                disputes.append({
                    "session_id": session_data.sid,
                    "attacker": msg.agent,
                    "finding": desc,
                    "severity": finding.get("severity", "unknown"),
                    "test_input": finding.get("test_input"),
                    "rebuttal": rebuttal,
                })

    # Extract Judge rulings from summary_json
    summary = session_data.summary_json or {}
    quality_report = session_data.quality_report_json or {}
    resolved = set(quality_report.get("resolved_issues", []))
    unresolved_descs = {
        item.get("description", ""): item
        for item in quality_report.get("unresolved_issues", [])
    }

    for dispute in disputes:
        desc = dispute["finding"]
        if desc in resolved or any(desc in r for r in resolved):
            dispute["judge_ruling"] = "must_fix"
        elif desc in unresolved_descs or any(desc in u for u in unresolved_descs):
            dispute["judge_ruling"] = "acknowledged"
        else:
            dispute["judge_ruling"] = "dismissed"

    return disputes


# ---------------------------------------------------------------------------
# Method 1: Human Label Comparison
# ---------------------------------------------------------------------------

def load_human_labels() -> list[dict]:
    """Load human-annotated arbitration labels."""
    if not HUMAN_LABELS_PATH.exists():
        logger.warning(
            "Human labels file not found at %s. "
            "Create it with arbitration ground truth data.",
            HUMAN_LABELS_PATH,
        )
        return []
    with open(HUMAN_LABELS_PATH) as f:
        return json.load(f)


async def method1_human_comparison() -> dict:
    """
    Compare Arbitrator rulings against human-annotated ground truth.

    Returns overall accuracy, must_fix precision, and dismissed precision.
    """
    human_labels = load_human_labels()
    if not human_labels:
        return {
            "method": "human_label_comparison",
            "status": "skipped",
            "reason": f"No human labels found at {HUMAN_LABELS_PATH}",
        }

    async with async_session() as session:
        db_sessions = await _load_completed_sessions(session)

    # Build lookup: session_id -> disputes
    session_disputes: dict[str, list[dict]] = {}
    for db_sess in db_sessions:
        disputes = _extract_disputes(db_sess)
        if disputes:
            session_disputes[db_sess.sid] = disputes

    total = 0
    correct = 0
    must_fix_tp = 0
    must_fix_fp = 0
    must_fix_fn = 0
    dismissed_tp = 0
    dismissed_fp = 0
    dismissed_fn = 0
    details = []

    for label in human_labels:
        sid = label["session_id"]
        human_verdict = label["human_verdict"]
        finding_desc = label.get("finding", "")

        # Find the matching dispute from DB
        disputes = session_disputes.get(sid, [])
        matched_dispute = None
        for d in disputes:
            if finding_desc and finding_desc.lower() in d["finding"].lower():
                matched_dispute = d
                break
            if d.get("dispute_id") == label.get("dispute_id"):
                matched_dispute = d
                break

        if matched_dispute is None:
            details.append({
                "label": label,
                "status": "no_matching_dispute_in_db",
            })
            continue

        judge_ruling = matched_dispute.get("judge_ruling", "unknown")
        total += 1
        is_correct = _verdicts_match(judge_ruling, human_verdict)
        if is_correct:
            correct += 1

        # must_fix precision/recall
        if human_verdict == "must_fix":
            if judge_ruling == "must_fix":
                must_fix_tp += 1
            else:
                must_fix_fn += 1
        elif judge_ruling == "must_fix":
            must_fix_fp += 1

        # dismissed precision/recall
        if human_verdict == "dismissed":
            if judge_ruling == "dismissed":
                dismissed_tp += 1
            else:
                dismissed_fn += 1
        elif judge_ruling == "dismissed":
            dismissed_fp += 1

        details.append({
            "session_id": sid,
            "finding": finding_desc,
            "human_verdict": human_verdict,
            "judge_ruling": judge_ruling,
            "correct": is_correct,
        })

    return {
        "method": "human_label_comparison",
        "total_compared": total,
        "overall_accuracy": round(correct / max(total, 1), 4),
        "must_fix_precision": round(
            must_fix_tp / max(must_fix_tp + must_fix_fp, 1), 4
        ),
        "must_fix_recall": round(
            must_fix_tp / max(must_fix_tp + must_fix_fn, 1), 4
        ),
        "dismissed_precision": round(
            dismissed_tp / max(dismissed_tp + dismissed_fp, 1), 4
        ),
        "dismissed_recall": round(
            dismissed_tp / max(dismissed_tp + dismissed_fn, 1), 4
        ),
        "details": details,
    }


def _verdicts_match(judge_ruling: str, human_verdict: str) -> bool:
    """Check if judge ruling matches human verdict (with normalization)."""
    EQUIVALENT = {
        "must_fix": {"must_fix", "critical", "required"},
        "dismissed": {"dismissed", "false_positive", "not_applicable"},
        "acknowledged": {"acknowledged", "deferred", "needs_human", "optional"},
    }
    for canonical, variants in EQUIVALENT.items():
        if judge_ruling in variants and human_verdict in variants:
            return True
    return judge_ruling == human_verdict


# ---------------------------------------------------------------------------
# Method 2: Code Verification
# ---------------------------------------------------------------------------

async def method2_code_verification() -> dict:
    """
    For disputes with test_input, run the test in Docker sandbox.

    If the test triggers a bug, the Arbitrator should NOT have dismissed it.
    If the test passes, dismissal was correct.
    """
    async with async_session() as session:
        db_sessions = await _load_completed_sessions(session)

    all_disputes = []
    for db_sess in db_sessions:
        disputes = _extract_disputes(db_sess)
        # Only keep disputes that have test_input and final code
        for d in disputes:
            if d.get("test_input") and db_sess.result_code:
                d["final_code"] = db_sess.result_code
                all_disputes.append(d)

    if not all_disputes:
        return {
            "method": "code_verification",
            "status": "skipped",
            "reason": "No disputes with test_input found in completed sessions.",
        }

    results = []
    correct_rulings = 0
    incorrect_rulings = 0

    for dispute in all_disputes:
        test_result = await _run_test_in_sandbox(
            dispute["final_code"],
            dispute["test_input"],
        )

        bug_triggered = test_result["returncode"] != 0
        judge_ruling = dispute.get("judge_ruling", "unknown")

        # Evaluate correctness of the ruling
        if bug_triggered and judge_ruling == "dismissed":
            verdict = "incorrect_dismissal"
            incorrect_rulings += 1
        elif not bug_triggered and judge_ruling == "dismissed":
            verdict = "correct_dismissal"
            correct_rulings += 1
        elif bug_triggered and judge_ruling in ("must_fix", "acknowledged"):
            verdict = "correct_must_fix"
            correct_rulings += 1
        elif not bug_triggered and judge_ruling in ("must_fix", "acknowledged"):
            verdict = "false_alarm_accepted"
            incorrect_rulings += 1
        else:
            verdict = "inconclusive"

        results.append({
            "session_id": dispute["session_id"],
            "attacker": dispute["attacker"],
            "finding": dispute["finding"],
            "judge_ruling": judge_ruling,
            "bug_triggered": bug_triggered,
            "verdict": verdict,
            "test_stdout": test_result.get("stdout", "")[:500],
            "test_stderr": test_result.get("stderr", "")[:500],
        })

    total = correct_rulings + incorrect_rulings
    return {
        "method": "code_verification",
        "total_verified": total,
        "correct_rulings": correct_rulings,
        "incorrect_rulings": incorrect_rulings,
        "accuracy": round(correct_rulings / max(total, 1), 4),
        "details": results,
    }


async def _run_test_in_sandbox(
    code: str,
    test_input: str,
    timeout: int = 15,
) -> dict:
    """Run a test snippet against the code in Docker sandbox."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = f"{tmpdir}/solution.py"
        test_path = f"{tmpdir}/test_dispute.py"

        with open(code_path, "w") as f:
            f.write(code)

        test_code = (
            "import sys\n"
            "sys.path.insert(0, '.')\n"
            "from solution import *\n\n"
            f"def test_dispute():\n"
            f"    {test_input}\n"
        )
        with open(test_path, "w") as f:
            f.write(test_code)

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "--rm",
                "--network=none",
                "--read-only",
                "--memory=256m",
                "--cpus=0.5",
                "-v", f"{tmpdir}:/workspace:ro",
                "-w", "/workspace",
                "--tmpfs", "/tmp:size=64m",
                "autojudge-sandbox:latest",
                "python", "-m", "pytest", "test_dispute.py",
                "-v", "--tb=short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return {
                "returncode": proc.returncode,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
            }
        except asyncio.TimeoutError:
            return {"returncode": 1, "stdout": "", "stderr": "Execution timed out"}
        except FileNotFoundError:
            logger.error(
                "Docker not found. Code verification requires Docker for sandbox."
            )
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Docker not available",
            }


# ---------------------------------------------------------------------------
# Method 3: LLM-as-Judge (placeholder)
# ---------------------------------------------------------------------------

async def method3_llm_as_judge(api_key: str | None = None) -> dict:
    """
    Use a separate LLM to evaluate whether the Arbitrator's ruling was correct.

    NOTE: Requires API key to run. Without an API key, this method returns
    a placeholder structure showing the expected input/output format.

    The LLM receives:
      - The disputed finding (attacker's claim)
      - The coder's rebuttal (evidence against)
      - The Arbitrator's ruling
      - The final code

    And is asked to independently judge whether the ruling was correct.
    """
    if not api_key:
        return {
            "method": "llm_as_judge",
            "status": "requires_api_key",
            "reason": (
                "This method requires an API key to call a separate LLM. "
                "Pass api_key parameter or set ANTHROPIC_API_KEY env var."
            ),
            "expected_input_format": {
                "dispute": {
                    "attacker": "security",
                    "finding": "SQL injection via string concatenation",
                    "severity": "critical",
                    "test_input": "'; DROP TABLE users; --",
                },
                "rebuttal": {
                    "explanation": "We use parameterized queries",
                    "evidence": "See line 42: cursor.execute(sql, params)",
                },
                "arbitrator_ruling": "dismissed",
                "final_code": "... code snippet ...",
            },
            "expected_output_format": {
                "llm_verdict": "must_fix | dismissed | acknowledged",
                "confidence": 0.85,
                "reasoning": "The rebuttal is incorrect because...",
                "agrees_with_arbitrator": False,
            },
        }

    # When API key is available, run actual LLM evaluation
    async with async_session() as session:
        db_sessions = await _load_completed_sessions(session)

    all_disputes = []
    for db_sess in db_sessions:
        disputes = _extract_disputes(db_sess)
        for d in disputes:
            d["final_code"] = db_sess.result_code or ""
            all_disputes.append(d)

    if not all_disputes:
        return {
            "method": "llm_as_judge",
            "status": "no_disputes",
            "reason": "No disputes found in completed sessions.",
        }

    from app.llm.client import call_agent

    results = []
    agrees_count = 0

    for dispute in all_disputes[:20]:  # Limit to 20 to control cost
        prompt = (
            "You are an expert code reviewer acting as an independent judge.\n\n"
            f"Attacker ({dispute['attacker']}) raised this finding:\n"
            f"  Finding: {dispute['finding']}\n"
            f"  Severity: {dispute['severity']}\n"
            f"  Test input: {dispute.get('test_input', 'N/A')}\n\n"
            f"Coder's rebuttal:\n"
            f"  {dispute.get('rebuttal', {}).get('explanation', 'N/A')}\n\n"
            f"Arbitrator ruled: {dispute.get('judge_ruling', 'unknown')}\n\n"
            f"Final code:\n```\n{dispute['final_code'][:2000]}\n```\n\n"
            "Based on the evidence, what is your independent verdict? "
            "Respond with: must_fix, dismissed, or acknowledged."
        )

        try:
            response = await call_agent(
                agent="eval_judge",
                system_prompt=(
                    "You are an impartial code review judge. Evaluate whether "
                    "the arbitrator's ruling on a disputed finding was correct. "
                    "Use the tool to submit your verdict."
                ),
                messages=[{"role": "user", "content": prompt}],
                tools=[{
                    "name": "submit_verdict",
                    "description": "Submit your independent verdict",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "verdict": {
                                "type": "string",
                                "enum": ["must_fix", "dismissed", "acknowledged"],
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "reasoning": {"type": "string"},
                        },
                        "required": ["verdict", "confidence", "reasoning"],
                    },
                }],
                tool_choice={"type": "tool", "name": "submit_verdict"},
                max_tokens=500,
            )

            llm_verdict = response.structured or {}
            agrees = _verdicts_match(
                dispute.get("judge_ruling", ""),
                llm_verdict.get("verdict", ""),
            )
            if agrees:
                agrees_count += 1

            results.append({
                "session_id": dispute["session_id"],
                "finding": dispute["finding"],
                "arbitrator_ruling": dispute.get("judge_ruling"),
                "llm_verdict": llm_verdict.get("verdict"),
                "llm_confidence": llm_verdict.get("confidence"),
                "llm_reasoning": llm_verdict.get("reasoning"),
                "agrees_with_arbitrator": agrees,
            })
        except Exception as e:
            logger.warning("LLM-as-Judge failed for dispute: %s", e)
            results.append({
                "session_id": dispute["session_id"],
                "finding": dispute["finding"],
                "error": str(e),
            })

    valid = [r for r in results if "error" not in r]
    return {
        "method": "llm_as_judge",
        "total_evaluated": len(valid),
        "agreement_rate": round(agrees_count / max(len(valid), 1), 4),
        "details": results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_arbitration_eval(api_key: str | None = None) -> dict:
    """Run all three arbitration evaluation methods and combine results."""
    logger.info("Starting arbitration evaluation...")

    method1_result = await method1_human_comparison()
    logger.info("Method 1 (Human Labels) complete: %s", method1_result.get("status", "done"))

    method2_result = await method2_code_verification()
    logger.info("Method 2 (Code Verification) complete: %s", method2_result.get("status", "done"))

    method3_result = await method3_llm_as_judge(api_key=api_key)
    logger.info("Method 3 (LLM-as-Judge) complete: %s", method3_result.get("status", "done"))

    return {
        "method1_human_comparison": method1_result,
        "method2_code_verification": method2_result,
        "method3_llm_as_judge": method3_result,
    }


async def main():
    """Entry point for running the evaluation."""
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    report = await run_arbitration_eval(api_key=api_key)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main())
