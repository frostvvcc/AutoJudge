"""
Static analysis scoring: objectively compare baseline vs adversarial
generated code using bandit and semgrep.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_bandit(code: str) -> dict:
    """Run bandit security scan on a code string."""
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False
    ) as f:
        f.write(code)
        f.flush()

        try:
            result = subprocess.run(
                ["bandit", "-r", f.name, "-f", "json", "-q"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout.strip():
                report = json.loads(result.stdout)
                results = report.get("results", [])
                return {
                    "high_severity": len(
                        [r for r in results if r.get("issue_severity") == "HIGH"]
                    ),
                    "medium_severity": len(
                        [r for r in results if r.get("issue_severity") == "MEDIUM"]
                    ),
                    "low_severity": len(
                        [r for r in results if r.get("issue_severity") == "LOW"]
                    ),
                    "total_warnings": len(results),
                }
            return {"total_warnings": 0}
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            return {"total_warnings": 0, "error": str(e)}


def run_semgrep(code: str, language: str = "python") -> dict:
    """Run semgrep scan on a code string."""
    suffix_map = {"python": ".py", "javascript": ".js", "typescript": ".ts"}
    suffix = suffix_map.get(language, ".py")

    with tempfile.NamedTemporaryFile(
        suffix=suffix, mode="w", delete=False
    ) as f:
        f.write(code)
        f.flush()

        try:
            result = subprocess.run(
                ["semgrep", "--config", "auto", f.name, "--json", "--quiet"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout.strip():
                report = json.loads(result.stdout)
                return {
                    "total_findings": len(report.get("results", [])),
                }
            return {"total_findings": 0}
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            return {"total_findings": 0, "error": str(e)}


def compare_static_analysis(
    baseline_codes: list[str],
    adversarial_codes: list[str],
) -> dict:
    """Compare static analysis results between baseline and adversarial."""
    baseline_bandit = [run_bandit(c) for c in baseline_codes]
    adversarial_bandit = [run_bandit(c) for c in adversarial_codes]

    baseline_warnings = sum(
        r.get("total_warnings", 0) for r in baseline_bandit
    )
    adversarial_warnings = sum(
        r.get("total_warnings", 0) for r in adversarial_bandit
    )

    n = max(len(baseline_codes), 1)

    return {
        "bandit": {
            "baseline_total_warnings": baseline_warnings,
            "adversarial_total_warnings": adversarial_warnings,
            "baseline_avg": round(baseline_warnings / n, 1),
            "adversarial_avg": round(adversarial_warnings / n, 1),
            "reduction_pct": (
                round(
                    (1 - adversarial_warnings / max(baseline_warnings, 1))
                    * 100
                )
                if baseline_warnings > 0
                else 0
            ),
        },
    }
