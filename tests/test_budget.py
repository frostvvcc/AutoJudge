import pytest
from app.engine.budget import BudgetManager


def test_initial_state():
    bm = BudgetManager(100_000)
    assert bm.total == 100_000
    assert bm.spent == 0
    assert bm.can_continue()


def test_record_tokens():
    bm = BudgetManager(10_000)
    bm.record("coder", 2000)
    bm.record("security", 1500)
    assert bm.spent == 3500
    assert bm.by_agent["coder"] == 2000
    assert bm.by_agent["security"] == 1500


def test_can_continue_with_reserve():
    bm = BudgetManager(10_000)
    bm.record("coder", 8000)
    assert bm.can_continue(reserve=0.15) is True
    bm.record("security", 700)
    assert bm.can_continue(reserve=0.15) is False


def test_get_max_tokens_respects_agent_limit():
    bm = BudgetManager(100_000)
    assert bm.get_max_tokens("coder") == 4000
    assert bm.get_max_tokens("security") == 2000
    assert bm.get_max_tokens("cross_review") == 1000


def test_get_max_tokens_respects_remaining():
    bm = BudgetManager(5000)
    bm.record("coder", 4000)
    max_tokens = bm.get_max_tokens("security")
    assert max_tokens <= 500


def test_record_cache():
    bm = BudgetManager(100_000)
    bm.record_cache("coder", cache_read=500, cache_creation=200)
    assert bm.cache_stats["read"] == 500
    assert bm.cache_stats["creation"] == 200


def test_remaining():
    bm = BudgetManager(10_000)
    bm.record("coder", 3000)
    assert bm.remaining() == 7000


def test_get_metrics():
    bm = BudgetManager(10_000)
    bm.record("coder", 2000)
    bm.record("security", 1000)
    bm.record_latency(500)
    metrics = bm.get_metrics()
    assert metrics["total_tokens"] == 3000
    assert "coder" in metrics["tokens_by_agent"]
    assert metrics["cost_usd"] > 0
