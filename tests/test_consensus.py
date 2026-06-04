import pytest
from app.engine.consensus import ConsensusDetector
from app.engine.context import DebateMessage


@pytest.fixture
def detector():
    return ConsensusDetector()


def _msg(agent: str, stance: str) -> DebateMessage:
    return DebateMessage(
        agent=agent,
        content="test",
        round=1,
        structured={"stance": stance, "findings": [], "has_new_issues": stance == "attacking", "message": "test"},
    )


def test_all_satisfied(detector):
    messages = [
        _msg("security", "satisfied"),
        _msg("performance", "satisfied"),
        _msg("correctness", "satisfied"),
    ]
    result = detector.check_consensus(messages)
    assert result["converged"] is True
    assert all(result["status"].values())


def test_one_attacking(detector):
    messages = [
        _msg("security", "satisfied"),
        _msg("performance", "attacking"),
        _msg("correctness", "satisfied"),
    ]
    result = detector.check_consensus(messages)
    assert result["converged"] is False
    assert result["status"]["performance"] is False


def test_all_attacking(detector):
    messages = [
        _msg("security", "attacking"),
        _msg("performance", "attacking"),
        _msg("correctness", "attacking"),
    ]
    result = detector.check_consensus(messages)
    assert result["converged"] is False


def test_empty_messages(detector):
    result = detector.check_consensus([])
    assert result["converged"] is False


def test_non_attacker_messages_ignored(detector):
    messages = [
        DebateMessage(agent="coder", content="code", round=1, structured={"stance": "satisfied"}),
        _msg("security", "satisfied"),
        _msg("correctness", "satisfied"),
    ]
    result = detector.check_consensus(messages)
    assert "coder" not in result["status"]


def test_missing_structured(detector):
    messages = [
        DebateMessage(agent="security", content="test", round=1, structured=None),
    ]
    result = detector.check_consensus(messages)
    assert result["converged"] is False
