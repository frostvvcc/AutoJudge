"""
Round 2: tasks specifically designed so the "obvious fix" is wrong.

The fix for these issues requires understanding a non-obvious invariant,
not just patching the symptom. Coder's first attempt is likely to fix
the symptom but miss the root cause → Arbitrator says "not_fixed".
"""

import asyncio
import sys
import os
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_strategy_v2")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


TASKS = [
    {
        "name": "Circular buffer with overwrite semantics",
        "requirement": (
            "实现一个 Python 类 CircularBuffer(capacity)。\n"
            "方法：write(data) 写入数据，read() 读出最早写入的数据。\n"
            "关键约束：\n"
            "- buffer 满时 write 必须覆盖最早的未读数据（不是抛异常）\n"
            "- read 空 buffer 抛 BufferEmptyError\n"
            "- write 后 read 的顺序必须严格 FIFO\n"
            "- capacity=1 时 write 两次然后 read 应该得到第二次的值\n"
            "- 连续 write N 次（N > capacity）后 read capacity 次，应得到最后 capacity 个值\n"
            "不允许使用 collections.deque，必须用固定长度数组实现。"
        ),
    },
    {
        "name": "Interval merge with open/closed boundaries",
        "requirement": (
            "实现一个 Python 函数 merge_intervals(intervals)。\n"
            "每个 interval 是 (start, end, start_open, end_open) 四元组，\n"
            "start_open/end_open 是 bool，True 表示开区间端点。\n"
            "规则：\n"
            "- [1,3] 和 [3,5] 合并为 [1,5]（闭+闭=重叠）\n"
            "- [1,3) 和 (3,5] 不合并（开+开=不接触）\n"
            "- [1,3) 和 [3,5] 合并为 [1,5]（开+闭=接触）\n"
            "- 空列表返回空列表\n"
            "- 单个区间原样返回\n"
            "返回合并后的列表，按 start 升序。"
        ),
    },
    {
        "name": "Topological sort with cycle detection",
        "requirement": (
            "实现一个 Python 函数 topological_sort(graph)。\n"
            "graph 是邻接表 dict，key 是节点，value 是依赖列表。\n"
            "例如 {'a': ['b', 'c'], 'b': ['c'], 'c': []} 表示 a 依赖 b 和 c。\n"
            "要求：\n"
            "- 有环时抛 CycleError，错误信息必须包含环路径如 'a -> b -> a'\n"
            "- 自环（'a' 依赖 'a'）也要检测\n"
            "- graph 中不存在的依赖节点视为无依赖节点\n"
            "- 返回列表，依赖在前（被依赖的排前面）\n"
            "- 同层级节点按字母顺序排列\n"
            "不允许使用任何第三方图库。"
        ),
    },
]


async def try_task(task_info: dict) -> dict:
    from app.engine.graph import run_debate_with_graph
    from app.engine.context import DebateConfig

    events = []
    fix_attempts = []
    strategy_changes = []
    review_results = []

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
            logger.info(f"  🔄 策略多样化触发! reason={event.get('reason', '')[:80]}")
        elif etype == "status":
            msg = event.get("content", "")
            logger.info(f"  ℹ {msg[:100]}")
            if "未修好" in msg or "未完全修复" in msg:
                review_results.append("not_fixed")
            elif "复核" in msg and "完成" not in msg:
                review_results.append("reviewing")
        elif etype == "arbitration_complete":
            logger.info(f"  ⚖ verdict={event.get('overall_verdict')}, disputes={event.get('disputes_count')}")
        elif etype == "message":
            agent = event.get("agent", "")
            if agent != "coder" or "修复" in (event.get("content", "") or "")[:20]:
                logger.info(f"  💬 [{agent}] R{event.get('round', '?')}")

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
        "review_had_not_fixed": "not_fixed" in review_results,
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
            logger.info(f"  fix={r['fix_attempts']}, diversify={r['strategy_changes']}, review_not_fixed={r['review_had_not_fixed']}")
            logger.info(f"  convergence={r['convergence_reason'][:80]}")

            if r["triggered_diversification"]:
                logger.info(f"\n  🎉🎉🎉 策略多样化已触发！停止尝试。")
                break
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
            nf = "✅" if r.get("review_had_not_fixed") else "⬜"
            print(f"  {r['name']}:")
            print(f"    final_fix={fix}  Arb复核未通过={nf}  策略多样化={div}")
            print(f"    attempts={r['fix_attempts']} changes={r['strategy_changes']} | {r['elapsed']:.0f}s")
            print(f"    {r['convergence_reason'][:80]}")

    any_diversified = any(r.get("triggered_diversification") for r in results)
    any_final_fix = any(r.get("triggered_final_fix") for r in results)
    any_not_fixed = any(r.get("review_had_not_fixed") for r in results)

    print()
    if any_diversified:
        print("  🎉 策略多样化路径已被真实触发并验证！")
    elif any_not_fixed:
        print("  ⚠️ Arbitrator 复核说过'未修好'，但策略多样化事件未被捕获")
    elif any_final_fix:
        print("  ⚠️ 进了 final_fix 但每次都一次修好了")
    else:
        print("  ⬜ final_fix 都没进入")


if __name__ == "__main__":
    asyncio.run(main())
