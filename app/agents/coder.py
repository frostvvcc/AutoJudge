from __future__ import annotations

from app.agents.base import BaseAgent, SAFETY_SUFFIX
from app.engine.context import DebateContext
from app.llm.client import CODER_TOOLS


class CoderAgent(BaseAgent):
    name = "coder"
    role = "代码构建者"

    def get_system_prompt(self, context: DebateContext) -> str:
        base = """你是代码的作者和维护者。你的职责：
1. 根据需求生成初版代码
2. 面对攻击时，如果攻击合理 → 承认并修复；如果攻击不合理 → 用证据反驳
3. 每次修复后贴出完整的新版代码
4. 你可以反驳任何 Attacker 的观点，但必须给出具体理由
5. 使用 submit_response 工具提交你的回应

代码提交要求（极其重要）：
- updated_code 必须是需求的完整实现——包含所有类、函数、import，一个不少
- updated_code 是生产代码，不是测试脚本、不是 demo 片段、不是写文件的包装脚本
- 代码必须是纯 Python 源码，直接可以保存为 .py 文件运行
- 修复时在上一版代码基础上修改，不要重写整个文件
- 回应攻击时 finding_ref 必须使用 Attacker 提供的 finding ID（如 SECURITY-001）

重要：你不是被动的修理工。如果你认为某个攻击不合理，大胆反驳，并说明理由。"""

        parts = [base]

        if context.parsed_requirement and isinstance(context.parsed_requirement, dict):
            req = context.parsed_requirement
            parts.append(
                f"\n需求分析：\n"
                f"功能点：{req.get('functional', [])}\n"
                f"约束：{req.get('constraints', [])}\n"
                f"隐式需求：{req.get('implicit', [])}\n"
                f"边界场景：{req.get('edge_cases', [])}"
            )

        if context.preference_context:
            parts.append(f"\n{context.preference_context}")

        if context.current_code:
            parts.append(f"\n当前最新代码版本：\n```\n{context.current_code}\n```")

        parts.append(SAFETY_SUFFIX.format(role=self.role))

        return "\n".join(parts)

    def get_tools(self) -> list[dict]:
        return CODER_TOOLS

    def get_tool_choice(self) -> dict:
        return {"type": "any"}
