from __future__ import annotations

from app.agents.base import BaseAgent, SAFETY_SUFFIX
from app.engine.context import DebateContext
from app.llm.client import ATTACKER_SUBMIT_TOOL


class CorrectnessAttacker(BaseAgent):
    name = "correctness"
    role = "正确性攻击者"

    def get_system_prompt(self, context: DebateContext) -> str:
        base = """你是质量工程师，专门找逻辑错误和边界问题。你的职责：
1. 关注边界输入、类型错误、竞态条件、错误处理、业务逻辑遗漏
2. 每个发现必须包含准确的行号 line_start 和 line_end（从 1 开始），指向代码中具体有问题的行
3. 给出能触发问题的具体输入（test_input 字段）和预期 vs 实际行为
4. 你可以支持其他 Attacker 的发现并补充新的角度
5. 如果 Coder 反驳了你的观点，评估反驳是否合理，合理就承认
6. 当你认为正确性没有问题时，stance 设为 "satisfied"
7. 你审查的对象是代码，不是方案设计文档。只针对实际代码中存在的问题提 finding

重点关注：
- 空值 / None / undefined 处理
- 边界条件（空列表、超长字符串、零、负数、最大整数）
- 类型错误（字符串拼接数字、隐式类型转换）
- 竞态条件（并发读写、先查后改）
- 错误处理遗漏（异常未捕获、错误码未检查）
- 业务逻辑遗漏（缺少的 else 分支、未处理的枚举值）

每个发现请尽量给出 test_input 字段，包含能触发问题的具体代码。"""

        parts = [base]

        if context.experience_context:
            parts.append(f"\n{context.experience_context}")

        if context.current_code:
            parts.append(f"\n当前代码：\n```\n{context.current_code}\n```")

        parts.append(SAFETY_SUFFIX.format(role=self.role))

        return "\n".join(parts)

    def get_tools(self) -> list[dict]:
        return [ATTACKER_SUBMIT_TOOL]

    def get_tool_choice(self) -> dict:
        return {"type": "tool", "name": "submit_review"}
