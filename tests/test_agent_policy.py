"""Privileged tools must be opt-in, not merely prompt-governed."""

from app.agent.tutor_tools import openai_tools, run_tool


def test_privileged_tools_are_hidden_by_default():
    names = {tool["function"]["name"] for tool in openai_tools()}
    assert {"db_query", "db_modify", "run_code", "plot_chart"}.isdisjoint(names)


def test_disabled_privileged_tool_cannot_be_dispatched():
    assert run_tool(None, 1, "db_modify", {"sql": "DELETE FROM users"}) == {
        "error": "tool 'db_modify' is disabled by local agent policy"
    }
