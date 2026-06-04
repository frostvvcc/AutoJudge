import pytest
from app.engine.context import DebateContext, DebateConfig


def test_add_message():
    ctx = DebateContext("test requirement")
    ctx.round = 1
    ctx.add_message("coder", "hello", code="print('hello')")
    assert len(ctx.messages) == 1
    assert ctx.current_code == "print('hello')"
    assert len(ctx.code_versions) == 1


def test_code_versions_accumulate():
    ctx = DebateContext("test")
    ctx.round = 1
    ctx.add_message("coder", "v1", code="v1_code")
    ctx.round = 2
    ctx.add_message("coder", "v2", code="v2_code")
    assert len(ctx.code_versions) == 2
    assert ctx.current_code == "v2_code"


def test_get_context_for_agent_alternation():
    ctx = DebateContext("test")
    ctx.round = 1
    ctx.add_message("coder", "initial code", code="code1")
    ctx.add_message("security", "found issue")
    ctx.add_message("performance", "no issues")

    messages = ctx.get_context_for_agent("security")
    roles = [m["role"] for m in messages]

    for i in range(len(roles) - 1):
        assert roles[i] != roles[i + 1], f"Consecutive same roles at index {i}"


def test_get_context_for_agent_ends_with_user():
    ctx = DebateContext("test")
    ctx.round = 1
    ctx.add_message("coder", "code")
    ctx.add_message("security", "issue found")

    messages = ctx.get_context_for_agent("security")
    if messages[-1]["role"] == "assistant":
        pytest.fail("Last message should be user to trigger agent reply")


def test_get_transcript():
    ctx = DebateContext("test")
    ctx.round = 1
    ctx.add_message("coder", "v1", code="code1")
    ctx.add_message("security", "issue1")
    ctx.round = 2
    ctx.add_message("coder", "v2", code="code2")

    transcript = ctx.get_transcript()
    assert len(transcript) == 2
    assert transcript[0]["round"] == 1
    assert len(transcript[0]["messages"]) == 2
    assert transcript[1]["round"] == 2


def test_empty_context():
    ctx = DebateContext("test")
    messages = ctx.get_context_for_agent("coder")
    assert len(messages) >= 1
    assert messages[-1]["role"] == "user"
