"""
Repeatedly attempt different tasks to trigger strategy diversification.

Goal: Coder fixes → Arbitrator review says "not_fixed" → switch angle → retry.
We try multiple tasks designed to produce hard-to-fix-correctly issues.
"""

import asyncio
import sys
import os
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_strategy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


TASKS = [
    {
        "name": "LRU Cache with O(1)",
        "requirement": (
            "实现一个 Python 类 LRUCache，支持 get(key) 和 put(key, value) 操作，"
            "要求两个操作都是 O(1) 时间复杂度。容量为 capacity。"
            "不允许使用 collections.OrderedDict。"
            "必须自己实现双向链表。"
        ),
    },
    {
        "name": "Date parser with edge cases",
        "requirement": (
            "实现一个 Python 函数 parse_date(s)，解析以下格式的日期字符串并返回 (year, month, day) 元组：\n"
            "支持格式：'2024-02-29', '02/29/2024', 'Feb 29, 2024', '29-Feb-2024'\n"
            "必须正确处理闰年判断（能被4整除但不能被100整除，或能被400整除）。\n"
            "无效日期返回 None。不允许使用 datetime 模块。"
        ),
    },
    {
        "name": "Expression evaluator",
        "requirement": (
            "实现一个 Python 函数 evaluate(expr)，计算包含 +, -, *, / 和括号的数学表达式字符串。\n"
            "要求：支持负数、小数、嵌套括号、运算符优先级。\n"
            "除以零返回 None。无效表达式抛出 ValueError。\n"
            "不允许使用 eval()、exec()、ast.literal_eval() 或任何第三方库。"
        ),
    },
]


async def try_task(task_info: dict) -> dict:
    from app.engine.graph import run_debate_with_graph
    from app.engine.context import DebateConfig

    events = []
    fix_attempts = []
    strategy_changes = []

    async def on_progress(event):
        events.append(event)
        etype = event.get("type", "")
        if etype == "phase_change":
            logger.info(f"  ▶ PHASE: {event.get('phase')}")
        elif etype == "fix_progress":
            fix_attempts.append(event)
            logger.info(f"  🔧 修复尝试 {event.get('attempt')}/{event.get('max_attempts')}")
        elif etype == "strategy_change":
            strategy_changes.append(event)
            logger.info(f"  🔄 策略多样化! angle={event.get('alternative', '')[:50]}")
        elif etype == "status":
            logger.info(f"  ℹ {event.get('content', '')[:80]}")
        elif etype == "arbitration_complete":
            logger.info(f"  ⚖ verdict={event.get('overall_verdict')}, disputes={event.get('disputes_count')}")

    config = DebateConfig(
        max_rounds=1,
        attackers=["correctness"],
        max_tokens=80_000,
        skip_cross_review=True,
    )

    start = time.monotonic()
    result = await run_debate_with_graph(
        requirement=task_info["requirement"],
        language="python",
        config=config,
        on_progress=on_progress,
    )
    elapsed = time.monotonic() - start

    return {
        "name": task_info["name"],
        "elapsed": elapsed,
        "fix_attempts": len(fix_attempts),
        "strategy_changes": len(strategy_changes),
        "convergence_reason": result.convergence_reason,
        "confidence": result.confidence,
        "code_len": len(result.code),
        "star": result.quality_report.star_rating,
        "triggered_final_fix": len(fix_attempts) > 0,
        "triggered_diversification": len(strategy_changes) > 0,
    }


async def main():
    from app.db.redis import init_redis, close_redis
    await init_redis()

    results = []

    for i, task in enumerate(TASKS):
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"ATTEMPT {i+1}/{len(TASKS)}: {task['name']}")
        logger.info("=" * 70)

        try:
            r = await try_task(task)
            results.append(r)

            logger.info(f"")
            logger.info(f"  fix_attempts={r['fix_attempts']}, strategy_changes={r['strategy_changes']}")
            logger.info(f"  convergence={r['convergence_reason']}")
            logger.info(f"  confidence={r['confidence']}, star={r['star']}")

            if r["triggered_diversification"]:
                logger.info(f"")
                logger.info(f"  🎉🎉🎉 策略多样化已触发！停止尝试。")
                break

            if r["triggered_final_fix"] and not r["triggered_diversification"]:
                logger.info(f"  ⚠️ 进了 final_fix 但第1次就修好了，策略多样化未触发")

        except Exception as e:
            logger.error(f"  ❌ 任务失败: {e}")
            results.append({"name": task["name"], "error": str(e)})

    await close_redis()

    print("\n")
    print("=" * 70)
    print("                         汇总")
    print("=" * 70)
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['name']}: {r['error'][:60]}")
        else:
            div = "✅" if r["triggered_diversification"] else "⬜"
            fix = "✅" if r["triggered_final_fix"] else "⬜"
            print(f"  {div} {r['name']}: final_fix={fix} diversify={div} attempts={r['fix_attempts']} changes={r['strategy_changes']} | {r['elapsed']:.0f}s")

    any_diversified = any(r.get("triggered_diversification") for r in results)
    if any_diversified:
        print("\n  🎉 策略多样化路径已被真实触发！")
    else:
        print("\n  ⬜ 策略多样化未触发（Coder 每次都一次修好了）")


if __name__ == "__main__":
    asyncio.run(main())
