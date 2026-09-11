"""Typed tool dispatch: validation at the boundary, structured errors."""

from app.agent.tutor_tools import (
    TOOLS,
    FindVideosArgs,
    run_tool,
)


class FakeDB:
    def get(self, _model, _id):
        return object()


def test_missing_required_is_structured_error_not_exception():
    r = run_tool(FakeDB(), 1, "record_understanding", {"demonstrated": 0.5})
    assert "error" in r and "topic_id" in r["error"]


def test_garbage_type_is_structured_error():
    r = run_tool(FakeDB(), 1, "record_understanding",
                 {"topic_id": "not-an-int", "demonstrated": 0.5, "coverage": 0.2})
    assert "error" in r


def test_valid_call_passes_through():
    r = run_tool(FakeDB(), 1, "ask_clarify", {"question": "Which topic?"})
    assert r["type"] == "clarify" and r["question"] == "Which topic?"


def test_explicit_null_falls_back_to_function_default():
    d = FindVideosArgs(query="x", count=None).model_dump(exclude_none=True)
    assert d == {"query": "x"}  # no count key -> function default applies


def test_unknown_tool():
    assert "error" in run_tool(FakeDB(), 1, "nope", {})


def test_args_models_cover_declared_params():
    # No silent drift: every typed field must exist in the hand-written
    # LLM-facing schema for the same tool.
    for name, spec in TOOLS.items():
        model = spec.get("args_model")
        if model is None:
            continue
        declared = set(spec["parameters"].get("properties", {}))
        for field_name in model.model_fields:
            assert field_name in declared or field_name == "confirmed", (
                name, field_name,
            )
