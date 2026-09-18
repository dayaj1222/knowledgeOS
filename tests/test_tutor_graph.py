"""The public synchronous tutor path is routed through the LangGraph state graph."""

from app.agent import tutor


def test_run_tutor_turn_delegates_to_graph(monkeypatch):
    expected = {"conversation_id": 4, "reply": "Hello"}
    seen = {}

    def fake_run(*args):
        seen["args"] = args
        return expected

    monkeypatch.setattr(tutor, "run_graph_turn", fake_run)
    assert tutor.run_tutor_turn("db", 1, None, "Hi", {"route": "/"}, ["image"]) == expected
    assert seen["args"] == ("db", 1, None, "Hi", {"route": "/"}, ["image"])


def test_streaming_turn_setup_delegates_to_graph(monkeypatch):
    """SSE must share the graph-backed conversation setup with JSON chat."""
    from app.agent import graph

    monkeypatch.setattr(graph, "open_turn_graph", type("Graph", (), {"invoke": lambda *_: {
        "conversation_id": 4, "messages": [{"role": "user", "content": "Hi"}], "thread_id": "thread"
    }})())
    assert graph.open_graph_turn("db", 1, None, "Hi") == (
        4, [{"role": "user", "content": "Hi"}], "thread"
    )
