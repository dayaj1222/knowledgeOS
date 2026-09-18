"""Module-pool RAG: the single retrieval truth for tutor tools, quiz
grounding, and video verification.

Passages are NEVER filed under topics. Each module's chunks (plus
course-level material of the same course) form one pool; callers rank
within the pool — vector cosine first, deterministic keyword fallback —
and expand context by contiguous index_order ranges.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models


def module_pool(db: Session, module_id: int) -> tuple[list[models.Passage], models.Module | None]:
    """All chunks of one module: module-scoped resources + course-level
    (module_id NULL, same course) fallback. Returns (passages, module)."""
    module = db.get(models.Module, int(module_id))
    if module is None:
        return [], None
    res_ids = db.scalars(
        select(models.Resource.id).where(
            (models.Resource.module_id == module.id)
            | (
                models.Resource.module_id.is_(None)
                & (models.Resource.course_id == module.course_id)
            )
        )
    ).all()
    if not res_ids:
        return [], module
    passages = db.scalars(
        select(models.Passage)
        .where(models.Passage.resource_id.in_(res_ids))
        .order_by(models.Passage.resource_id, models.Passage.index_order)
    ).all()
    return passages, module


def pool_counts(db: Session, module_ids: list[int]) -> dict[int, int]:
    """Map module_id -> chunk count in its pool (grouped queries).

    Includes course-level material (module_id NULL): it belongs to every
    pool of that course, so it is counted in each.
    """
    if not module_ids:
        return {}
    modules = db.scalars(
        select(models.Module).where(models.Module.id.in_(module_ids))
    ).all()
    by_course: dict[int, list[int]] = {}
    for m in modules:
        by_course.setdefault(m.course_id, []).append(m.id)
    direct = dict(
        db.execute(
            select(models.Resource.module_id, func.count(models.Passage.id))
            .join(models.Passage, models.Passage.resource_id == models.Resource.id)
            .where(models.Resource.module_id.in_(module_ids))
            .group_by(models.Resource.module_id)
        ).all()
    )
    out: dict[int, int] = {}
    for course_id, mids in by_course.items():
        shared = db.scalar(
            select(func.count(models.Passage.id))
            .join(models.Resource, models.Passage.resource_id == models.Resource.id)
            .where(
                models.Resource.module_id.is_(None),
                models.Resource.course_id == course_id,
            )
        ) or 0
        for mid in mids:
            out[mid] = direct.get(mid, 0) + shared
    return out


def _keyword_rank(query: str, passages: list[models.Passage], top: int) -> list[tuple[models.Passage, str]]:
    """Deterministic keyword fallback when vectors are unavailable."""
    from ..ingest.tagger import score_chunk, topic_terms

    terms = topic_terms(query, "")
    scored = [
        (score_chunk(p.content, p.section_path or "", terms)[0], p)
        for p in passages
    ]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [(p, "keyword") for s, p in scored[:top] if s > 0]


def rank_pool(
    db: Session, query: str, passages: list[models.Passage], top: int
) -> list[tuple[models.Passage, str]]:
    """Vector cosine first, keyword fallback. Returns [(passage, match)]."""
    if not passages or not query.strip():
        return []
    try:
        from ..ingest.embeddings import embed_texts, rank

        ids = [p.id for p in passages]
        rows = db.execute(
            select(models.PassageEmbedding.passage_id, models.PassageEmbedding.vec)
            .where(models.PassageEmbedding.passage_id.in_(ids))
        ).all()
        vec_rows = [(pid, bytes(vec)) for pid, vec in rows]
        if vec_rows:
            q = embed_texts([query])[0]
            by_id = {p.id: p for p in passages}
            return [
                (by_id[pid], "vector")
                for pid, _ in rank(q, vec_rows, top)
                if pid in by_id
            ]
    except Exception:
        pass
    return _keyword_rank(query, passages, top)


def grounding_for_topic(db: Session, topic: models.Topic, top: int = 6) -> list[str]:
    """Chunk texts grounding one topic: its module pool ranked by the
    topic's own name+description. Used by quiz synthesis and video verify."""
    if topic.module_id is None:
        return []
    passages, module = module_pool(db, topic.module_id)
    if module is None:
        return []
    query = topic.name + " " + (topic.description or "")
    return [p.content for p, _ in rank_pool(db, query, passages, top)]
