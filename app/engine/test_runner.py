from __future__ import annotations

import asyncio
import tempfile
import logging
from dataclasses import dataclass, field

from app.engine.context import DebateContext
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    passed: bool
    reason: str
    test_code: str = ""
    stdout: str = ""
    stderr: str = ""
    tests_passed: int = 0
    tests_failed: int = 0
    test_sources: dict = field(default_factory=dict)


class TestRunner:
    """
    Lightweight runtime verification for final code:
    1. Syntax check (can it parse?)
    2. LLM generates basic test cases
    3. Sandbox execution
    4. Verification failure → feedback to Coder for one more fix
    """

    async def verify(
        self,
        code: str,
        requirement: str,
        llm_client,
        debate_context: DebateContext | None = None,
        language: str = "python",
    ) -> VerifyResult:
        syntax_error = await self.check_syntax(code, language)
        if syntax_error:
            return VerifyResult(
                passed=False, reason="语法错误", stderr=syntax_error
            )

        adversarial_tests = []
        if debate_context:
            adversarial_tests = self._extract_attacker_test_cases(
                debate_context
            )

        generated_tests = await self.generate_tests(
            code, requirement, llm_client
        )

        combined = self._merge_tests(adversarial_tests, generated_tests)

        exec_result = await self.run_in_sandbox(code, combined, timeout=15)

        passed_count = exec_result.stdout.count("PASSED")
        failed_count = exec_result.stdout.count("FAILED")

        return VerifyResult(
            passed=exec_result.returncode == 0,
            reason="测试通过" if exec_result.returncode == 0 else "测试失败",
            test_code=combined,
            stdout=exec_result.stdout,
            stderr=exec_result.stderr,
            tests_passed=passed_count,
            tests_failed=failed_count,
            test_sources={
                "adversarial": len(adversarial_tests),
                "generated": 1,
            },
        )

    async def check_syntax(
        self, code: str, language: str
    ) -> str | None:
        if language == "python":
            try:
                compile(code, "<generated>", "exec")
                return None
            except SyntaxError as e:
                return f"SyntaxError at line {e.lineno}: {e.msg}"
        return None

    async def generate_tests(
        self, code: str, requirement: str, llm_client
    ) -> str:
        from app.llm.client import call_agent

        response = await call_agent(
            agent="test_generator",
            system_prompt=(
                "你是测试工程师。为给定代码生成 pytest 测试用例，"
                "覆盖正常路径和边界情况。只输出测试代码，不要解释。"
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"为以下代码生成 pytest 测试用例：\n\n"
                        f"需求：{requirement}\n\n"
                        f"代码：\n```python\n{code}\n```"
                    ),
                }
            ],
            tools=[
                {
                    "name": "submit_tests",
                    "description": "提交测试代码",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "test_code": {
                                "type": "string",
                                "description": "完整的 pytest 测试代码",
                            }
                        },
                        "required": ["test_code"],
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "submit_tests"},
            model=settings.haiku_model,
            max_tokens=2000,
        )

        if response.structured and "test_code" in response.structured:
            return response.structured["test_code"]
        return response.content

    def _extract_attacker_test_cases(
        self, context: DebateContext
    ) -> list[str]:
        test_cases = []
        for msg in context.messages:
            if msg.agent != "correctness":
                continue
            if msg.structured and isinstance(msg.structured, dict):
                for finding in msg.structured.get("findings", []):
                    if finding.get("test_input"):
                        test_cases.append(
                            self._finding_to_test(finding)
                        )
        return test_cases

    def _finding_to_test(self, finding: dict) -> str:
        return (
            f"def test_adversarial_{finding.get('category', 'unknown')}():\n"
            f"    # Source: Correctness Attacker\n"
            f"    # Expected: {finding['description']}\n"
            f"    {finding['test_input']}\n"
        )

    def _merge_tests(
        self, adversarial: list[str], generated: str
    ) -> str:
        parts = [generated]
        if adversarial:
            parts.append("\n# === Adversarial Test Cases ===\n")
            parts.extend(adversarial)
        return "\n\n".join(parts)

    async def run_in_sandbox(
        self, code: str, test_code: str, timeout: int = 15
    ) -> _ExecResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            code_path = f"{tmpdir}/solution.py"
            test_path = f"{tmpdir}/test_solution.py"

            with open(code_path, "w") as f:
                f.write(code)
            with open(test_path, "w") as f:
                f.write(f"import sys; sys.path.insert(0, '.')\nfrom solution import *\n\n{test_code}")

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
                    "python", "-m", "pytest", "test_solution.py",
                    "-v", "--tb=short",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                return _ExecResult(
                    returncode=proc.returncode,
                    stdout=stdout.decode(),
                    stderr=stderr.decode(),
                )
            except asyncio.TimeoutError:
                return _ExecResult(
                    returncode=1, stdout="", stderr="执行超时"
                )
            except FileNotFoundError:
                logger.error(
                    "docker_not_found: Docker is required for sandbox execution"
                )
                return _ExecResult(
                    returncode=1,
                    stdout="",
                    stderr="Docker is not available. Code verification requires Docker for sandbox isolation.",
                )


@dataclass
class _ExecResult:
    returncode: int
    stdout: str
    stderr: str
