"""
MCP Server for code analysis tools (bandit + semgrep).
Attackers call these tools via MCP protocol for real static analysis.

Run as a separate process:
    python -m app.mcp.servers.code_analysis
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)


async def bandit_scan(code: str, language: str = "python") -> dict:
    """Run bandit security scan on code snippet."""
    if language != "python":
        return {"results": [], "note": f"bandit only supports Python, got {language}"}

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
                return json.loads(result.stdout)
            return {"results": [], "errors": result.stderr}
        except FileNotFoundError:
            return {
                "results": [],
                "error": "bandit not installed",
            }
        except subprocess.TimeoutExpired:
            return {"results": [], "error": "scan timeout"}
        except json.JSONDecodeError:
            return {
                "results": [],
                "error": "invalid bandit output",
                "raw": result.stdout[:500],
            }


async def semgrep_scan(code: str, language: str = "python") -> dict:
    """Run semgrep scan on code snippet."""
    suffix_map = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "java": ".java",
        "go": ".go",
        "rust": ".rs",
    }
    suffix = suffix_map.get(language, ".py")

    with tempfile.NamedTemporaryFile(
        suffix=suffix, mode="w", delete=False
    ) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [
                    "semgrep",
                    "--config",
                    "auto",
                    f.name,
                    "--json",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout.strip():
                return json.loads(result.stdout)
            return {"results": [], "errors": result.stderr}
        except FileNotFoundError:
            return {
                "results": [],
                "error": "semgrep not installed",
            }
        except subprocess.TimeoutExpired:
            return {"results": [], "error": "scan timeout"}
        except json.JSONDecodeError:
            return {
                "results": [],
                "error": "invalid semgrep output",
            }
