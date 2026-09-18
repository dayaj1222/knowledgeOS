"""Module-pool RAG: scoping, range expansion, topic grounding, counts.

Contract: passages are never filed under topics. Each module's chunks
(+ course-level fallback) form one pool; search ranks within the pool;
context expands by contiguous index_order ranges.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.agent import tutor_tools
from app.database import Base
from app.services.retrieval import grounding_for_topic, pool_counts


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(models.User(id=1, name="t", email="t@t.t"))
        s.add(models.Course(id=1, user_id=1, name="Nets", code="NET"))
        s.add(models.Module(id=10, course_id=1, name="Routing"))
        s.add(models.Module(id=20, course_id=1, name="Switching"))
        s.add(models.Topic(id=100, module_id=10, name="Packet forwarding",
                           description="how routers forward packets"))
        s.add(models.Topic(id=200, module_id=20, name="VLANs",
                           description="virtual lans segment broadcast domains"))
        # Module-scoped resources + one course-level fallback.
        s.add(models.Resource(id=1, user_id=1, course_id=1, module_id=10,
                              name="r1", file_path="r1.pdf", status="done"))
        s.add(models.Resource(id=2, user_id=1, course_id=1, module_id=20,
                              name="r2", file_path="r2.pdf", status="done"))
        s.add(models.Resource(id=3, user_id=1, course_id=1, module_id=None,
                              name="r3", file_path="r3.pdf", status="done"))
        s.add(models.Passage(id=1, resource_id=1, index_order=0,
                             content="Routers forward packets by longest prefix match."))
        s.add(models.Passage(id=2, resource_id=1, index_order=1,
                             content="The forwarding table maps prefixes to next hops."))
        s.add(models.Passage(id=3, resource_id=1, index_order=2,
                             content="TTL is decremented at every router hop."))
        s.add(models.Passage(id=4, resource_id=2, index_order=0,
                             content="VLANs segment broadcast domains on switches."))
        s.add(models.Passage(id=5, resource_id=3, index_order=0,
                             content="Course overview: networks connect hosts."))
        s.commit()
        yield s


def _embed(db):
    from app.ingest.embeddings import MODEL_NAME, embed_texts, pack

    passages = db.query(models.Passage).order_by(models.Passage.id).all()
    for p, v in zip(passages, embed_texts([p.content for p in passages]), strict=True):
        db.add(models.PassageEmbedding(passage_id=p.id, model=MODEL_NAME, vec=pack(v)))
    db.commit()


def test_search_stays_in_module(db):
    out = tutor_tools.search_module(db, 1, {"module_id": 10, "query": "packets"})
    ids = [h["id"] for h in out]
    assert ids, "expected hits in Routing pool"
    assert 4 not in ids, "Switching chunk leaked into Routing pool"


def test_course_level_fallback_in_pool(db):
    out = tutor_tools.search_module(db, 1, {"module_id": 20, "query": "hosts networks"})
    assert any(h["id"] == 5 for h in out), "course-level chunk missing from pool"


def test_unknown_module_errors(db):
    assert tutor_tools.search_module(db, 1, {"module_id": 999, "query": "x"}) == {
        "error": "unknown_module"}


def test_range_exact_window_and_order(db):
    out = tutor_tools.get_passage_range(
        db, 1, {"resource_id": 1, "start": 0, "end": 2})
    assert [h["index_order"] for h in out] == [0, 1, 2]
    assert all(h["match"] == "context" for h in out)


def test_range_rejects_start_after_end(db):
    out = tutor_tools.get_passage_range(
        db, 1, {"resource_id": 1, "start": 2, "end": 0})
    assert out["error"].startswith("start must be")


def test_range_caps_window_at_15(db):
    for i in range(3, 25):
        db.add(models.Passage(id=100 + i, resource_id=1, index_order=i,
                              content=f"filler chunk {i}"))
    db.commit()
    out = tutor_tools.get_passage_range(
        db, 1, {"resource_id": 1, "start": 0, "end": 100})
    assert len(out) == 15


def test_topic_wrapper_grounds_without_filing(db):
    _embed(db)
    out = tutor_tools.get_passages(db, 1, {"topic_id": 100, "limit": 3})
    assert isinstance(out, list) and out
    # All routing-pool chunks, none from Switching — with no topic_id set.
    assert all(h["id"] in (1, 2, 3, 5) for h in out)
    assert db.query(models.Passage).filter(
        models.Passage.topic_id.is_not(None)).count() == 0


def test_topic_wrapper_unknown(db):
    assert tutor_tools.get_passages(db, 1, {"topic_id": 999}) == {
        "error": "unknown_topic"}


def test_vector_beats_keyword_on_paraphrase(db):
    """Golden mini-eval: paraphrased query must surface the right chunk."""
    _embed(db)
    out = tutor_tools.search_module(
        db, 1, {"module_id": 10, "query": "how does a router decide where to send a datagram"})
    assert out and out[0]["id"] in (1, 2), f"vector miss: {[h['id'] for h in out]}"


def test_keyword_fallback_when_vectors_missing(db):
    out = tutor_tools.search_module(db, 1, {"module_id": 10, "query": "forwarding table"})
    assert any(h["id"] == 2 for h in out)
    assert all(h["match"] == "keyword" for h in out)


def test_grounding_for_topic_used_by_quiz(db):
    topic = db.get(models.Topic, 200)
    texts = grounding_for_topic(db, topic)
    assert any("VLAN" in t for t in texts)


def test_pool_counts_include_course_level(db):
    counts = pool_counts(db, [10, 20])
    assert counts[10] == 4, counts  # 3 module + 1 course-level
    assert counts[20] == 2, counts  # 1 module + 1 course-level
