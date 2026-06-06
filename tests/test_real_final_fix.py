"""
Real integration test: trigger final_fix + strategy diversification path.

Strategy: use a task with obvious security flaws that attackers WILL flag,
set max_rounds=1 to force arbitration after 1 round, and observe whether
the full chain fires: arbitration → must_fix → final_fix → Arbitrator review.
"""

import asyncio
import sys
import os
import time
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test_final_fix")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_final_fix_path():
    """
    Task designed to trigger: arbitration → must_fix → final_fix → strategy diversification

    The task asks Coder to build something with a deliberate security concern
    (string concatenation for SQL), max_rounds=1 forces arbitration after 1 round,
    and we watch if the full fix/review/retry chain fires.
    """
    from app.engine.graph import run_debate_with_graph
    from app.engine.context import DebateConfig

    events = []
    phases_seen = []
    fix_attempts = []
    strategy_changes = []

    async def on_progress(event):
        events.append(event)
        etype = event.get("type", "")

        if etype == "phase_change":
            phases_seen.append(event.get("phase", ""))
            logger.info(f"  ▶ PHASE: {event.get('phase')}")
        elif etype == "status":
            logger.info(f"  ℹ {event.get('content', '')}")
        elif etype == "fix_progress":
            fix_attempts.append(event)
            logger.info(f"  🔧 修复尝试 {event.get('attempt')}/{event.get('max_attempts')}")
        elif etype == "strategy_change":
            strategy_changes.append(event)
            logger.info(f"  🔄 策略多样化: {event.get('alternative', '')}")
            logger.info(f"     原因: {event.get('reason', '')[:100]}")
        elif etype == "message":
            agent = event.get("agent", "")
            r = event.get("round", "?")
            content_preview = (event.get("content") or "")[:80]
            logger.info(f"  💬 [{agent}] R{r}: {content_preview}...")
        elif etype == "arbitration_complete":
            logger.info(f"  ⚖ 仲裁完成: verdict={event.get('overall_verdict')}, disputes={event.get('disputes_count')}")
        elif etype in ("round_start", "converged", "done"):
            logger.info(f"  📡 {etype}: {event.get('content', event.get('round', ''))}")

    # max_rounds=1 → 1 round then arbitration
    # Only correctness attacker → avoids critical security findings
    # Goal: 1-3 must_fix at high/medium severity → triggers final_fix
    config = DebateConfig(
        max_rounds=1,
        attackers=["correctness"],
        max_tokens=100_000,
        skip_cross_review=True,
    )

    logger.info("=" * 70)
    logger.info("TEST: final_fix + 策略多样化路径")
    logger.info("  任务: 有边界 bug 的排序函数 (引导出 non-critical must_fix)")
    logger.info("  配置: max_rounds=1, attackers=[correctness]")
    logger.info("=" * 70)

    start = time.monotonic()
    result = await run_debate_with_graph(
        requirement=(
            "实现一个 Python 函数 merge_sorted_lists(list1, list2)，"
            "合并两个已排序列表并返回新的排序列表。"
            "要求处理空列表、重复元素、不同长度列表。"
            "不要使用内置 sorted() 函数。"
        ),
        language="python",
        config=config,
        on_progress=on_progress,
    )
    elapsed = time.monotonic() - start

    # ─── Analysis ───
    logger.info("")
    logger.info("=" * 70)
    logger.info("结果分析")
    logger.info("=" * 70)

    triggered_arbitration = "arbitration" in phases_seen
    has_arbitration_data = bool(result.metadata.get("arbitration"))
    has_must_fix = False
    must_fix_count = 0
    fix_attempt_count = len(fix_attempts)
    strategy_change_count = len(strategy_changes)

    if has_arbitration_data:
        arb = result.metadata["arbitration"]
        rulings = arb.get("rulings", [])
        must_fix_count = sum(1 for r in rulings if r.get("verdict") == "must_fix")
        has_must_fix = must_fix_count > 0
        logger.info(f"  仲裁裁决详情:")
        for r in rulings:
            logger.info(f"    [{r.get('verdict')}] {r.get('re_assessed_severity', '?')} — {r.get('dispute_id', '?')}")
            logger.info(f"      理由: {r.get('reasoning', '')[:100]}")

    logger.info(f"")
    logger.info(f"  ┌─────────────────────────────────────────────┐")
    logger.info(f"  │ 总耗时:              {elapsed:.1f}s")
    logger.info(f"  │ 代码长度:            {len(result.code)} 字符")
    logger.info(f"  │ 总 tokens:           {result.metrics.total_tokens}")
    logger.info(f"  │ 总轮次:              {result.metrics.total_rounds}")
    logger.info(f"  │ 收敛:                {result.converged}")
    logger.info(f"  │ 收敛原因:            {result.convergence_reason}")
    logger.info(f"  │ confidence:          {result.confidence}")
    logger.info(f"  │ star_rating:         {result.quality_report.star_rating}")
    logger.info(f"  │ phases 经过:         {phases_seen}")
    logger.info(f"  │")
    logger.info(f"  │ 触发仲裁:            {'✅ Yes' if triggered_arbitration else '❌ No'}")
    logger.info(f"  │ 有 must_fix:         {'✅ Yes (' + str(must_fix_count) + '条)' if has_must_fix else '❌ No'}")
    logger.info(f"  │ 进入 final_fix:      {'✅ Yes' if fix_attempt_count > 0 else '❌ No'}")
    logger.info(f"  │ 修复尝试次数:        {fix_attempt_count}")
    logger.info(f"  │ 策略多样化触发:      {'✅ Yes (' + str(strategy_change_count) + '次)' if strategy_change_count > 0 else '❌ No'}")
    logger.info(f"  │ requires_human:      {result.metadata.get('requires_human_review', False)}")
    logger.info(f"  └─────────────────────────────────────────────┘")

    if result.code:
        logger.info(f"")
        logger.info(f"  代码前 400 字符:")
        for line in result.code[:400].split("\n"):
            logger.info(f"    {line}")

    # ─── Path coverage check ───
    logger.info(f"")
    logger.info(f"路径覆盖检查:")
    paths = {
        "plan → coder":           True,
        "attackers 并行":         any(e.get("type") == "message" and e.get("agent") in ("security", "correctness") for e in events),
        "仲裁触发":               triggered_arbitration,
        "must_fix 裁决":          has_must_fix,
        "final_fix 进入":         fix_attempt_count > 0,
        "策略多样化":             strategy_change_count > 0,
        "judge 报告":             result.confidence > 0,
    }
    for path, covered in paths.items():
        status = "✅" if covered else "⬜"
        logger.info(f"  {status} {path}")

    all_critical_covered = triggered_arbitration and has_must_fix and fix_attempt_count > 0
    if all_critical_covered:
        logger.info(f"\n  🎉 final_fix 路径已被真实触发并验证！")
    elif triggered_arbitration and not has_must_fix:
        logger.info(f"\n  ⚠️ 仲裁触发了但没有 must_fix 裁决 — Arbitrator 认为争议不需要强制修复")
        logger.info(f"     这取决于 LLM 的判断，不是代码 bug")
    elif not triggered_arbitration:
        logger.info(f"\n  ⚠️ 仲裁未触发 — 可能 1 轮后所有攻击者都 satisfied 了")


async def main():
    from app.db.redis import init_redis, close_redis
    await init_redis()
    try:
        await test_final_fix_path()
    except Exception as e:
        logger.error(f"❌ FAILED: {e}", exc_info=True)
    await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
