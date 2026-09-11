"""Tutor tool implementations — plain functions over the service layer.

Each entry: TOOLS[name] = {"signature": ..., "description": ..., "run": fn}.
`run(db, user_id, args)` returns a JSON-serializable result. Mutating tools
honor the confirm-in-chat rule via the `confirmed` arg.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .. import models
from ..config import settings
from ..services import (
    CHAT_UNDERSTANDING,
    CourseService,
    ProficiencyService,
    QuizService,
    ReviewService,
    ScheduleService,
    StudyService,
)
from ..services.review_service import score_to_quality
from .web import fetch_transcript as _fetch_transcript
from .web import fetch_url as _fetch_url
from .web import score_relevance as _score_relevance
from .web import search_videos as _search_videos
from .web import search_web as _search_web


def _needs_confirmation(action: str, params: dict) -> dict:
    return {"needs_confirmation": True, "action": action, "params": params}


# ---------- typed args (runtime validation at dispatch) ----------
# NOTE: these mirror runtime behavior (defaults, coercions), NOT the
# aspirational hand-written JSON schemas in TOOLS (which carry richer
# per-field docs for the model). A test locks field parity so they can't
# drift apart silently. New tools MUST declare an args model.


class RecordUnderstandingArgs(BaseModel):
    topic_id: int
    demonstrated: float = 0.8
    coverage: float = 0.2
    evidence: str = ""
    confirmed: bool = False


class UpdateTodoArgs(BaseModel):
    todos: list[dict]
    confirmed: bool = False


class GenerateQuizArgs(BaseModel):
    topic_ids: list[int] = Field(default_factory=list)
    count_per_topic: int | None = None
    difficulty: str | None = None
    confirmed: bool = False


class AskClarifyArgs(BaseModel):
    question: str = ""
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True


class AskReviewArgs(BaseModel):
    items: list[dict]


class FindVideosArgs(BaseModel):
    query: str
    count: int | None = None
    topic_id: int | None = None


class StartTimerArgs(BaseModel):
    topic_id: int
    label: str = ""


# ---------- read-only ----------

def search_knowledge(db, user_id: int, args: dict) -> list[dict]:
    query = str(args.get("query", ""))
    limit = min(int(args.get("limit", 5)), 15)
    like = f"%{query}%"
    out: list[dict] = []
    for p in db.scalars(
        select(models.Passage).where(models.Passage.content.ilike(like)).limit(limit)
    ).all():
        out.append(
            {
                "kind": "passage",
                "id": p.id,
                "topic_id": p.topic_id,
                "pages": [p.page_start, p.page_end],
                "snippet": p.content[:400],
            }
        )
    for t in db.scalars(
        select(models.Topic).where(models.Topic.name.ilike(like)).limit(limit)
    ).all():
        out.append({"kind": "topic", "id": t.id, "name": t.name})
    for q in db.scalars(
        select(models.Question).where(models.Question.text.ilike(like)).limit(limit)
    ).all():
        out.append(
            {"kind": "question", "id": q.id, "topic_id": q.topic_id, "text": q.text[:300]}
        )
    return out[: limit * 2]


def list_courses(db, user_id: int, args: dict) -> list[dict]:
    courses = db.scalars(
        select(models.Course).where(models.Course.user_id == user_id)
    ).all()
    return [{"id": c.id, "name": c.name, "code": c.code} for c in courses]


def course_tree(db, user_id: int, course_id: int) -> dict | None:
    """Full course structure in one shot: modules with nested topics, each
    topic carrying its id, proficiency score, and passage count. Shared by
    the get_course_tree tool and the per-turn snapshot injection."""
    course = db.get(models.Course, course_id)
    if course is None or course.user_id != user_id:
        return None
    scores = {
        r.topic_id: round(r.score, 2)
        for r in db.scalars(
            select(models.Proficiency).where(models.Proficiency.user_id == user_id)
        ).all()
    }
    counts = dict(
        db.execute(
            select(models.Passage.topic_id, func.count(models.Passage.id))
            .join(models.Resource, models.Passage.resource_id == models.Resource.id)
            .where(models.Resource.user_id == user_id)
            .group_by(models.Passage.topic_id)
        ).all()
    )
    modules = db.scalars(
        select(models.Module)
        .where(models.Module.course_id == course_id)
        .order_by(models.Module.order_index, models.Module.id)
    ).all()
    out_modules = []
    for m in modules:
        topics = db.scalars(
            select(models.Topic)
            .where(models.Topic.module_id == m.id)
            .order_by(models.Topic.order_index, models.Topic.id)
        ).all()
        out_modules.append(
            {
                "id": m.id,
                "name": m.name,
                "topics": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "score": scores.get(t.id),
                        "passages": counts.get(t.id, 0),
                    }
                    for t in topics
                ],
            }
        )
    return {"id": course.id, "name": course.name, "code": course.code, "modules": out_modules}


def get_course_tree(db, user_id: int, args: dict) -> dict:
    """One call for the full picture: modules with nested topics (ids,
    proficiency scores, passage counts). Replaces the old
    list_courses → list_modules → list_topics chain."""
    try:
        course_id = int(args["course_id"])
    except (TypeError, ValueError, KeyError):
        return {"error": "course_id (int) required — use list_courses to find it"}
    tree = course_tree(db, user_id, course_id)
    if tree is None:
        return {"error": f"course {args.get('course_id')} not found"}
    return tree


def get_passages(db, user_id: int, args: dict) -> list[dict]:
    limit = min(int(args.get("limit", 6)), 12)
    passages = db.scalars(
        select(models.Passage)
        .where(models.Passage.topic_id == int(args["topic_id"]))
        .order_by(models.Passage.index_order)
        .limit(limit)
    ).all()
    return [
        {"id": p.id, "pages": [p.page_start, p.page_end], "section": p.section_path, "content": p.content[:1200]}
        for p in passages
    ]


def get_proficiency(db, user_id: int, args: dict) -> list[dict]:
    rows = db.scalars(
        select(models.Proficiency).where(models.Proficiency.user_id == user_id)
    ).all()
    out = []
    for r in rows:
        topic = db.get(models.Topic, r.topic_id)
        out.append(
            {
                "topic_id": r.topic_id,
                "topic": topic.name if topic else f"#{r.topic_id}",
                "score": round(r.score, 2),
                "weak_points": r.weak_points or [],
                "strengths": r.strengths or [],
            }
        )
    return sorted(out, key=lambda d: d["score"])


def get_weaknesses(db, user_id: int, args: dict) -> list[dict]:
    return QuizService.topic_weaknesses(db, user_id)


def recent_answers(db, user_id: int, args: dict) -> list[dict]:
    """Newest graded attempts with the learner's literal answers (read-only)."""
    topic_id = args.get("topic_id")
    try:
        limit = int(args.get("limit", 8))
    except (TypeError, ValueError):
        limit = 8
    return QuizService.recent_attempts(
        db, user_id,
        topic_id=int(topic_id) if topic_id is not None else None,
        limit=limit,
    )


def get_due_reviews(db, user_id: int, args: dict) -> list[dict]:
    limit = min(int(args.get("limit", 10)), 20)
    # ReviewService.due_queue already returns dicts (topic_id, topic_name,
    # due_date, ...). Reshape to the stable {topic_id, topic} contract.
    return [
        {"topic_id": d["topic_id"], "topic": d.get("topic_name", f"#{d['topic_id']}")}
        for d in ReviewService.due_queue(db, user_id, limit=limit)
    ]


def get_deadlines(db, user_id: int, args: dict) -> list[dict]:
    rows = db.scalars(
        select(models.Deadline)
        .where(models.Deadline.user_id == user_id)
        .order_by(models.Deadline.due_date)
        .limit(10)
    ).all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "due_date": str(d.due_date),
            "weight": d.weight,
            "course_id": d.course_id,
        }
        for d in rows
    ]


def recall(db, user_id: int, args: dict) -> list[dict]:
    mems = db.scalars(
        select(models.TutorMemory).where(models.TutorMemory.user_id == user_id)
    ).all()
    return [{"key": m.key, "value": m.value} for m in mems]


def remember(db, user_id: int, args: dict) -> dict:
    key, value = str(args["key"])[:128], str(args["value"])
    mem = db.scalar(
        select(models.TutorMemory).where(
            models.TutorMemory.user_id == user_id, models.TutorMemory.key == key
        )
    )
    if mem is None:
        mem = models.TutorMemory(user_id=user_id, key=key, value=value)
        db.add(mem)
    else:
        mem.value = value
    db.commit()
    return {"saved": True, "key": key}


def read_passage_notes(db, user_id: int, args: dict) -> list[dict] | dict:
    """Read tutor/learner annotations on passages (read-only)."""
    passage_id = args.get("passage_id")
    if passage_id is not None:
        notes = db.scalars(
            select(models.PassageNote).where(
                models.PassageNote.passage_id == int(passage_id),
                models.PassageNote.user_id == user_id,
            )
        ).all()
    else:
        try:
            limit = min(int(args.get("limit", 20)), 50)
        except (TypeError, ValueError):
            limit = 20
        notes = db.scalars(
            select(models.PassageNote)
            .where(models.PassageNote.user_id == user_id)
            .order_by(models.PassageNote.id.desc())
            .limit(limit)
        ).all()
    return [
        {"id": n.id, "passage_id": n.passage_id, "note": n.note}
        for n in notes
    ]


# ---------- web (read-only; implementations live in app/agent/web.py) ----------

def web_search(db, user_id: int, args: dict) -> dict:
    """Search the public web via DuckDuckGo (no key). No confirmation needed."""
    query = str(args.get("query", ""))
    try:
        count = int(args.get("count", 5))
    except (TypeError, ValueError):
        count = 5
    return _search_web(query, count)


def fetch_url(db, user_id: int, args: dict) -> dict:
    """Fetch a page's text content (the agent's 'curl'). No confirmation needed."""
    url = str(args.get("url", ""))
    try:
        max_chars = int(args.get("max_chars", 3000))
    except (TypeError, ValueError):
        max_chars = 3000
    return _fetch_url(url, max_chars)


def find_videos(db, user_id: int, args: dict) -> dict:
    """Find YouTube videos for a topic — renders INLINE as embedded players.
    No confirmation needed. Max 3 per call.

    Pass topic_id to VERIFY each video: its caption track is fetched and
    scored against the topic's own passages (keyword overlap). Verified
    videos genuinely cover the topic; the rest are flagged, not dropped —
    the tutor presents verified ones first and says so.
    """
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query must be non-empty (topic + concept, e.g. 'priority ceiling protocol explained')"}
    try:
        count = max(1, min(int(args.get("count", 3)), 5))
    except (TypeError, ValueError):
        count = 3
    result = _search_videos(query, count)
    videos = result.get("videos", [])
    if not videos:
        return {"videos": [], "hint": "No videos found — teach from passages instead."}
    # Verification: caption track vs the topic's own text.
    topic_text = ""
    topic_name = ""
    try:
        topic_id = int(args.get("topic_id")) if args.get("topic_id") is not None else None
    except (TypeError, ValueError):
        topic_id = None
    if topic_id is not None:
        topic = db.get(models.Topic, topic_id)
        if topic is not None:
            topic_name = topic.name or ""
            parts = [topic_name, topic.description or ""]
            for p in db.scalars(
                select(models.Passage)
                .where(models.Passage.topic_id == topic_id)
                .order_by(models.Passage.index_order)
                .limit(6)
            ).all():
                parts.append((p.content or "")[:800])
            topic_text = "\n".join(parts)
    for v in videos:
        v["verified"] = False
        v["relevance"] = 0.0
        if not topic_text:
            continue
        tr = _fetch_transcript(v["video_id"])
        if tr.get("error") or not tr.get("full_text"):
            v["verify_note"] = tr.get("error", "no transcript")[:120]
            continue
        scored = _score_relevance(tr["full_text"], topic_text, topic_name)
        v["relevance"] = scored["relevance"]
        v["matched"] = scored["matched"]
        v["verified"] = scored["relevance"] >= 0.3
    videos.sort(key=lambda v: (v["verified"], v["relevance"]), reverse=True)
    return {
        "type": "video",
        "videos": videos,
        "hint": (
            "These render INLINE as embedded players. Present VERIFIED videos "
            "first (their captions match the syllabus); say plainly when one "
            "is unverified. Introduce in 1-2 sentences (which video covers "
            "what), then end with: VIDEO_READY — do NOT paste raw URLs."
        ),
    }


# ---------- mutating (confirm-in-chat) ----------

def create_module(db, user_id: int, args: dict) -> dict:
    if not args.get("confirmed"):
        return _needs_confirmation(
            f"Create module '{args.get('name')}' in course {args.get('course_id')}", dict(args)
        )
    CourseService.require_course(db, int(args["course_id"]))
    mod = models.Module(course_id=int(args["course_id"]), name=str(args["name"]))
    db.add(mod)
    db.commit()
    db.refresh(mod)
    return {"created": True, "id": mod.id, "name": mod.name}


def create_topic(db, user_id: int, args: dict) -> dict:
    if not args.get("confirmed"):
        return _needs_confirmation(
            f"Create topic '{args.get('name')}' in module {args.get('module_id')}", dict(args)
        )
    CourseService.require_module(db, int(args["module_id"]))
    topic = models.Topic(module_id=int(args["module_id"]), name=str(args["name"]))
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return {"created": True, "id": topic.id, "name": topic.name}


async def generate_quiz(db, user_id: int, args: dict) -> dict:
    topic_ids = [int(t) for t in args.get("topic_ids", [])]
    # Omitted count/difficulty fall back to the user's Practice settings.
    pref = db.get(models.Preference, user_id)
    default_count = pref.default_quiz_count if pref and pref.default_quiz_count else 3
    default_diff = (pref.default_difficulty if pref and pref.default_difficulty else "medium")
    count = min(int(args.get("count_per_topic", default_count)), 10)
    difficulty = str(args.get("difficulty", default_diff))
    if not args.get("confirmed"):
        return _needs_confirmation(
            f"Generate {count} {difficulty} question(s) each for topics {topic_ids}", dict(args)
        )
    if not topic_ids:
        # No topic named: default to the learner's weakest topics so the quiz
        # is always grounded in what matters most right now.
        assessment, created = await QuizService.agenerate_drill(
            db, user_id, count=count, difficulty=difficulty
        )
    else:
        assessment, created = await QuizService.agenerate_quiz(
            db, user_id, topic_ids, count, difficulty=difficulty
        )
    return {
        "created": True,
        "type": "assessment",
        "assessment_id": assessment.id,
        "count": len(created),
        "question_ids": [q.id for q in created],
        "questions": [
            {
                "id": q.id,
                "topic_id": q.topic_id,
                "text": q.text,
                "type": q.type,
                "expected_key_points": q.expected_key_points or [],
            }
            for q in created
        ],
        "hint": (
            "This quiz renders INLINE in the chat. Introduce it briefly "
            "(1-2 sentences), then end with: QUIZ_READY — do NOT call "
            "ui_command open_quiz and do not paste the questions in text."
        ),
    }


def generate_study_plan(db, user_id: int, args: dict) -> dict:
    if not args.get("confirmed"):
        return _needs_confirmation("Regenerate the study plan (replaces pending items)", {})
    plans = ScheduleService.generate_plan(db, user_id)
    out = []
    for p in plans:
        topic = db.get(models.Topic, p.topic_id)
        out.append(
            {"topic": topic.name if topic else p.topic_id, "minutes": p.suggested_duration_minutes}
        )
    return {"created": True, "plans": out}


def log_study(db, user_id: int, args: dict) -> dict:
    if not args.get("confirmed"):
        return _needs_confirmation(
            f"Log {args.get('minutes_spent')} min of study on topic {args.get('topic_id')}",
            dict(args),
        )
    log = StudyService.log_study(
        db, user_id=user_id, topic_id=int(args["topic_id"]),
        minutes_spent=int(args["minutes_spent"]),
    )
    db.commit()
    return {"logged": True, "id": log.id}


def create_deadline(db, user_id: int, args: dict) -> dict:
    if not args.get("confirmed"):
        return _needs_confirmation(
            f"Add deadline '{args.get('title')}' due {args.get('due_date')}", dict(args)
        )
    d = models.Deadline(
        user_id=user_id,
        course_id=int(args["course_id"]),
        topic_id=int(args["topic_id"]) if args.get("topic_id") else None,
        title=str(args["title"]),
        due_date=datetime.fromisoformat(str(args["due_date"])),
        weight=float(args.get("weight", 1.0)),
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"created": True, "id": d.id, "title": d.title}


def take_passage_note(db, user_id: int, args: dict) -> dict:
    """MUTATING: pin an annotation to a passage. Propose first, save when confirmed."""
    text = str(args.get("note", "")).strip()
    if not args.get("confirmed"):
        return _needs_confirmation(
            f"Save a note on passage {args.get('passage_id')}: '{text[:120]}'",
            dict(args),
        )
    passage = db.get(models.Passage, int(args["passage_id"]))
    if passage is None:
        return {"error": f"passage {args.get('passage_id')} not found"}
    if not text:
        return {"error": "note must be non-empty"}
    note = models.PassageNote(
        passage_id=passage.id, user_id=user_id, note=text[:2000]
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"saved": True, "id": note.id, "passage_id": passage.id}


def ask_clarify(db, user_id: int, args: dict) -> dict:
    """Ask a disambiguating question — renders INLINE as a selection card
    (options tappable, free-text allowed). No confirmation needed."""
    question = str(args.get("question", "")).strip()[:500]
    options = [str(o).strip()[:120] for o in (args.get("options") or [])]
    options = [o for o in options if o][:4]
    allow_free_text = bool(args.get("allow_free_text", True))
    if not question:
        return {"error": "question must be non-empty"}
    return {
        "type": "clarify",
        "question": question,
        "options": options,
        "allow_free_text": allow_free_text,
        "hint": (
            "This renders INLINE as a selection card. Introduce it briefly "
            "(1-2 sentences), then end with: CLARIFY_READY — do NOT paste "
            "the options as a text list."
        ),
    }


def ask_review(db, user_id: int, args: dict) -> dict:
    """Run a spaced-repetition recall session — renders INLINE as flip cards
    (recall prompt → reveal key points → self-rate). No confirmation needed.

    items: [{topic_id, prompt, key_points[]}] — build ONE per due topic from
    get_due_reviews, with the prompt + key points grounded in that topic's
    passages. Max 8 items per session.
    """
    raw = args.get("items") or []
    # Cap the session at the user's Practice setting (default 8).
    pref = db.get(models.Preference, user_id)
    batch = pref.review_batch_size if pref and pref.review_batch_size else 8
    batch = max(1, min(int(batch), 15))
    items = []
    for it in raw[:batch]:
        if not isinstance(it, dict):
            continue
        try:
            topic_id = int(it.get("topic_id"))
        except (TypeError, ValueError):
            continue
        topic = db.get(models.Topic, topic_id)
        if topic is None:
            continue
        prompt = str(it.get("prompt", "")).strip()[:500]
        key_points = [str(k).strip()[:300] for k in (it.get("key_points") or [])]
        key_points = [k for k in key_points if k][:6]
        if not prompt or not key_points:
            continue
        items.append({
            "topic_id": topic_id,
            "topic_name": topic.name,
            "prompt": prompt,
            "key_points": key_points,
        })
    if not items:
        return {"error": "items must be non-empty: [{topic_id, prompt, key_points[]}] with grounded content"}
    return {
        "type": "review",
        "items": items,
        "hint": (
            "This renders INLINE as recall flip cards; each card self-grades "
            "straight into the SM-2 schedule. Introduce the session briefly "
            "(1-2 sentences), then end with: REVIEW_READY — do NOT paste the "
            "prompts or key points in text."
        ),
    }


def start_timer(db, user_id: int, args: dict) -> dict:
    """Start a study timer — renders as a live pill in the tutor header.
    The learner stops it when done; stopping auto-logs the study session.
    No confirmation needed. One active timer at a time."""
    try:
        topic_id = int(args["topic_id"])
    except (TypeError, ValueError, KeyError):
        return {"error": "topic_id (int) required"}
    topic = db.get(models.Topic, topic_id)
    if topic is None:
        return {"error": f"topic {args.get('topic_id')} not found"}
    label = str(args.get("label", "")).strip()[:120] or topic.name
    return {
        "type": "timer",
        "action": "start",
        "topic_id": topic_id,
        "topic_name": topic.name,
        "label": label,
        "hint": (
            "A live timer pill starts in the header. Say what to focus on in "
            "1-2 sentences, then end with: TIMER_STARTED — the learner stops "
            "it when done and the session logs automatically."
        ),
    }


def stop_timer(db, user_id: int, args: dict) -> dict:
    """Stop the active study timer from chat ('I'm done', 'stop the timer').
    The frontend logs the elapsed session automatically. No confirmation."""
    return {
        "type": "timer",
        "action": "stop",
        "hint": (
            "The timer pill stops and the session logs. Acknowledge briefly "
            "(1-2 sentences), then end with: TIMER_STOPPED."
        ),
    }


def update_todo(db, user_id: int, args: dict) -> dict:
    """Standard agent todo list — plan tracking for multi-step work.

    Call with the FULL list every time (not deltas): create the plan on the
    first step, then re-call with updated statuses as each step completes.
    Exactly ONE item may be in_progress; mark others pending/completed.
    No confirmation needed. Renders as a progress graph in the side panel.

    SESSION WORKFLOW (topic study): at the start of topic work, decompose
    the topic into one item per subtopic, each with a weight (share of the
    whole topic, weights normalized to sum 1.0; omit for equal shares).
    As each subtopic completes, score it with record_understanding using
    coverage = that item's weight — topic mastery is then the fair sum of
    weight × demonstrated over subtopics, so one slice can never swamp
    the whole score.
    """
    raw = args.get("todos") or []
    if not isinstance(raw, list) or not raw:
        return {"error": "todos must be a non-empty list: [{content, status, activeForm?, weight?}]"}
    items = []
    for it in raw[:20]:
        if not isinstance(it, dict):
            continue
        content = str(it.get("content", "")).strip()[:200]
        status = str(it.get("status", "pending")).strip().lower()
        if not content or status not in ("pending", "in_progress", "completed"):
            continue
        active = str(it.get("activeForm", "")).strip()[:200] or content
        try:
            weight = max(0.0, float(it.get("weight", 0.0)))
        except (TypeError, ValueError):
            weight = 0.0
        items.append({"content": content, "status": status, "activeForm": active, "weight": weight})
    if not items:
        return {"error": "no valid items (need content + status pending|in_progress|completed)"}
    if sum(1 for i in items if i["status"] == "in_progress") > 1:
        return {"error": "only ONE item may be in_progress — set the rest to pending/completed"}
    # Normalize shares: explicit weights scale to 1.0, otherwise equal splits.
    given = sum(i["weight"] for i in items)
    if given > 0:
        items = [{**i, "weight": round(i["weight"] / given, 4)} for i in items]
    else:
        items = [{**i, "weight": round(1.0 / len(items), 4)} for i in items]
    done = sum(1 for i in items if i["status"] == "completed")
    current = next((i for i in items if i["status"] == "in_progress"), None)
    return {
        "type": "todo",
        "todos": items,
        "total": len(items),
        "completed": done,
        "current": current["content"] if current else None,
        "current_active": current["activeForm"] if current else None,
        "hint": (
            "The side panel renders this as a progress graph. When a "
            "subtopic step completes, score it with record_understanding "
            "using coverage = that step's weight. Keep teaching in the reply "
            "text; never paste the todo list as text."
        ),
    }


#: Weight for chat-demonstrated understanding vs stored score per event.
#: Configured (proficiency.chat_alpha) so tuning never edits call sites.
LEARN_ALPHA = settings.proficiency.chat_alpha

#: Conservative default when the model omits coverage: a single chat answer
#: is one check question, a small slice of the whole topic — never the whole.
DEFAULT_COVERAGE = 0.2

#: Minimum coverage for a chat event to also count as an SM-2 recall event.
#: Nailing one subtopic must not push the whole topic's review schedule out.
REVIEW_MIN_COVERAGE = 0.5


def record_understanding(db, user_id: int, args: dict) -> dict:
    """Record understanding the learner demonstrated IN CHAT (a correct
    explanation, a good paraphrase, a right answer to a check question).
    Bumps proficiency immediately — no confirmation, never announced.

    Topic mastery from one slice = coverage * demonstrated: e.g. 0.85 on one
    subtopic of five (coverage 0.2) is 0.17 of the whole topic, not 0.85.
    Fresh topics start at demonstrated * coverage. Existing topics move a
    damped step toward demonstrated, scaled by coverage, so a slice nudges
    instead of jumping:
        score += LEARN_ALPHA * coverage * (demonstrated - score)
    """
    try:
        topic_id = int(args["topic_id"])
        demonstrated = max(0.0, min(1.0, float(args.get("demonstrated", 0.8))))
        coverage = max(0.0, min(1.0, float(args.get("coverage", DEFAULT_COVERAGE))))
    except (TypeError, ValueError, KeyError):
        return {"error": "topic_id (int) and demonstrated (0.0-1.0) required"}
    if coverage <= 0:
        return {"error": "coverage must be > 0 (what fraction of the topic did this cover?)"}
    evidence = str(args.get("evidence", ""))[:300]
    topic = db.get(models.Topic, topic_id)
    if topic is None:
        return {"error": f"topic {topic_id} not found"}
    alpha_eff = LEARN_ALPHA * coverage
    prof, _event = ProficiencyService.record(
        db,
        user_id=user_id,
        topic_id=topic_id,
        observed=demonstrated,
        alpha=alpha_eff,
        source=CHAT_UNDERSTANDING,
        evidence=f"coverage={coverage} {evidence}".strip(),
        fresh_value=demonstrated * coverage,
    )
    # Demonstrating recall counts for the SM-2 schedule only when a
    # substantial slice was tested — a single check question must not push
    # the whole topic's review date out.
    sm2_updated = False
    if coverage >= REVIEW_MIN_COVERAGE:
        ReviewService.record_result(
            db, user_id=user_id, topic_id=topic_id,
            quality=score_to_quality(demonstrated),
            source="chat",
        )
        sm2_updated = True
    if evidence and prof.strengths is not None and evidence not in (prof.strengths or []):
        prof.strengths = ([*(prof.strengths or []), evidence])[:8]
        db.add(prof)
    db.commit()
    return {
        "recorded": True,
        "topic_id": topic_id,
        "score": round(prof.score, 2),
        "observed": round(demonstrated * coverage, 2),
        "coverage": coverage,
        "sm2_updated": sm2_updated,
    }


# ---------- direct database access (the "modify db directly" power) ----------

_READ_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "PRAGMA")
_WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE")
_FORBIDDEN = ("DROP", "ALTER", "CREATE", "TRUNCATE", "ATTACH", "DETACH", "VACUUM", "REINDEX")


def _single_statement(sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    if not sql or ";" in sql:
        raise ValueError("One statement per call, no stacked queries.")
    return sql


def db_query(db, user_id: int, args: dict) -> dict:
    """Run a read-only SQL query. Returns {columns, rows (max 50), rowcount}."""
    from sqlalchemy import text as _text

    sql = _single_statement(str(args.get("sql", "")))
    first = sql.split(None, 1)[0].upper()
    if first not in _READ_PREFIXES:
        return {"error": f"db_query is read-only (got {first}). Use db_modify for writes."}
    try:
        result = db.execute(_text(sql))
        cols = list(result.keys())
        rows = [list(r) for r in result.fetchmany(50)]
        return {"columns": cols, "rows": rows, "truncated": result.fetchone() is not None}
    except Exception as e:  # noqa: BLE001 — DB errors go back to the model
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}


def db_modify(db, user_id: int, args: dict) -> dict:
    """Run a single INSERT/UPDATE/DELETE. Proposes first; executes when confirmed=true."""
    from sqlalchemy import text as _text

    sql = _single_statement(str(args.get("sql", "")))
    upper = sql.upper()
    if any(re.search(rf"\b{kw}\b", upper) for kw in _FORBIDDEN):
        return {"error": "Schema changes (DROP/ALTER/CREATE/...) are never allowed via chat."}
    first = sql.split(None, 1)[0].upper()
    if first not in _WRITE_PREFIXES:
        return {"error": f"db_modify accepts only INSERT/UPDATE/DELETE (got {first})."}
    if not args.get("confirmed"):
        return _needs_confirmation(f"Run SQL: {sql}", {"sql": sql})
    try:
        result = db.execute(_text(sql))
        db.commit()
        return {"executed": True, "rowcount": result.rowcount}
    except Exception as e:  # noqa: BLE001 — DB errors go back to the model
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}


TOOLS: dict[str, dict[str, Any]] = {
    "db_query": {
        "signature": '(sql: str)',
        "description": (
            "Run a read-only SQL query (SELECT/WITH) against the app database. "
            "Tables: users, courses, modules, topics, proficiency, resources, passages "
            "(id, resource_id, topic_id, content, index_order, page_start, page_end), "
            "passage_notes (id, passage_id, user_id, note, created_at), "
            "questions, assessments, attempts, preferences, schedules, slots, deadlines, "
            "reviews, plans, study_logs, conversations, chat_messages, tutor_memory. "
            "No confirmation needed. One statement, max 50 rows returned."
        ),
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
        "run": db_query,
    },
    "db_modify": {
        "signature": '(sql: str, confirmed?: bool)',
        "description": (
            "Run a single INSERT/UPDATE/DELETE directly on the database — cleanup, dedupe, "
            "fixing mis-tagged passages, anything no narrower tool covers. Call first with "
            "confirmed omitted/false to propose the exact SQL; re-call with confirmed=true "
            "only after the student says yes. Schema changes are blocked entirely."
        ),
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["sql"]},
        "run": db_modify,
    },
    "ui_command": {
        "signature": '(action: str, params?: object)',
        "description": (
            "Send a command to the app UI. Actions: navigate {route: / | /library | /plan | /settings} ; "
            "select_course {course_id}; reload {} to refresh sidebar data; notify {message} for a toast. "
            "Quizzes and reviews render INLINE in the chat — never navigate away for them. "
            "Navigation only — never needs confirmation. Call it AFTER the data tool succeeds."
        ),
        "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "params": {"type": "object"}}, "required": ["action"]},
        "run": lambda db, user_id, args: {"queued": True, **{k: v for k, v in args.items() if k != 'confirmed'}},
    },
    "search_knowledge": {
        "signature": '(query: str, limit?: int)',
        "description": "Full-text search over passages, topics, and questions.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]},
        "run": search_knowledge,
    },
    "web_search": {
        "signature": '(query: str, count?: int)',
        "description": (
            "Search the public web (DuckDuckGo + Wikipedia fallback, no key) for "
            "material outside the syllabus, current info, or extra examples. Prefer "
            "stored passages first; use this when local material is missing or the "
            "student asks for the web/latest."
        ),
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "count": {"type": "integer"}}, "required": ["query"]},
        "run": web_search,
    },
    "fetch_url": {
        "signature": '(url: str, max_chars?: int)',
        "description": (
            "Fetch a public web page's text content (http/https only, loopback blocked). "
            "Use after web_search to read a promising result in full. Returns truncated text."
        ),
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer"}}, "required": ["url"]},
        "run": fetch_url,
    },
    "find_videos": {
        "signature": '(query: str, count?: int, topic_id?: int)',
        "description": (
            "Find YouTube videos for a topic — renders INLINE as embedded "
            "players in the chat (thumbnail → click to play). Pass topic_id "
            "to VERIFY each video against the topic's passages (caption-track "
            "overlap; verified ones genuinely cover the syllabus). Use when "
            "the learner is stuck after explanations, asks for a video/visual, "
            "or a concept cries out for animation (protocols, algorithms, "
            "waveforms). Query with topic + concept words. Max 3-5 per call. "
            "No confirmation needed. Videos supplement the stored passages, "
            "never replace them — say which part each covers."
        ),
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "count": {"type": "integer"}, "topic_id": {"type": "integer"}}, "required": ["query"]},
        "run": find_videos,
        "args_model": FindVideosArgs,
    },
    "list_courses": {
        "signature": '()',
        "description": "List the learner's courses (id, name, code).",
        "parameters": {"type": "object", "properties": {}},
        "run": list_courses,
    },
    "get_course_tree": {
        "signature": '(course_id: int)',
        "description": (
            "Full course structure in ONE call: modules with nested topics, "
            "each topic carrying its id, proficiency score, and passage "
            "count. Hierarchy is Course > Module > Topic. Quiz, passage, "
            "review, and timer tools all take topic_id — module_id is only "
            "for create_topic. Prefer the per-turn snapshot tree when it "
            "covers the course you need; call this when it doesn't."
        ),
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}}, "required": ["course_id"]},
        "run": get_course_tree,
    },
    "get_passages": {
        "signature": '(topic_id: int, limit?: int)',
        "description": "Fetch stored passage text for a topic to ground explanations.",
        "parameters": {"type": "object", "properties": {"topic_id": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["topic_id"]},
        "run": get_passages,
    },
    "get_proficiency": {
        "signature": '()',
        "description": "Mastery scores per topic with weak/strong points.",
        "parameters": {"type": "object", "properties": {}},
        "run": get_proficiency,
    },
    "get_weaknesses": {
        "signature": '()',
        "description": "Topics with the most missed key points from graded attempts.",
        "parameters": {"type": "object", "properties": {}},
        "run": get_weaknesses,
    },
    "recent_answers": {
        "signature": '(topic_id?: int, limit?: int)',
        "description": (
            "Newest graded quiz attempts with the learner's LITERAL answers: "
            "question text, your_answer, expected key points, score, feedback, "
            "matched/missed points. Call this FIRST when the learner asks about "
            "a mistake — diagnose the exact misconception in their answer, never "
            "from aggregates alone. Omit topic_id for latest across all quizzes."
        ),
        "parameters": {"type": "object", "properties": {"topic_id": {"type": "integer"}, "limit": {"type": "integer"}}},
        "run": recent_answers,
    },
    "get_due_reviews": {
        "signature": '(limit?: int)',
        "description": "Spaced-repetition topics due now.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        "run": get_due_reviews,
    },
    "get_deadlines": {
        "signature": '()',
        "description": "Upcoming deadlines.",
        "parameters": {"type": "object", "properties": {}},
        "run": get_deadlines,
    },
    "recall": {
        "signature": '()',
        "description": "Read durable tutor memories about this learner.",
        "parameters": {"type": "object", "properties": {}},
        "run": recall,
    },
    "read_passage_notes": {
        "signature": '(passage_id?: int, limit?: int)',
        "description": (
            "Read tutor/learner annotations pinned to passages — clarifications, "
            "cross-concept links, misconception warnings. Pass passage_id for one "
            "passage's notes, or omit it for the most recent notes. Read these "
            "before re-explaining a topic so stored clarifications compound."
        ),
        "parameters": {"type": "object", "properties": {"passage_id": {"type": "integer"}, "limit": {"type": "integer"}}},
        "run": read_passage_notes,
    },
    "remember": {
        "signature": '(key: str, value: str)',
        "description": "Save a durable note about the learner. No confirmation needed.",
        "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]},
        "run": remember,
    },
    "create_module": {
        "signature": '(course_id: int, name: str, confirmed?: bool)',
        "description": "MUTATING: create a module. Call first with confirmed omitted/false to propose.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "name": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["course_id", "name"]},
        "run": create_module,
    },
    "create_topic": {
        "signature": '(module_id: int, name: str, confirmed?: bool)',
        "description": "MUTATING: create a topic. Call first with confirmed omitted/false to propose.",
        "parameters": {"type": "object", "properties": {"module_id": {"type": "integer"}, "name": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["module_id", "name"]},
        "run": create_topic,
    },
    "generate_quiz": {
        "signature": '(topic_ids?: int[], count_per_topic?: int, difficulty?: str, confirmed?: bool)',
        "description": (
            "MUTATING: generate practice questions — they render INLINE in the "
            "chat as sliding cards. Pass the topic_ids you are currently "
            "teaching (derive them from the conversation); omit topic_ids to "
            "target the learner's weakest topics. Propose first, execute when "
            "confirmed=true."
        ),
        "parameters": {"type": "object", "properties": {"topic_ids": {"type": "array", "items": {"type": "integer"}}, "count_per_topic": {"type": "integer"}, "difficulty": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": []},
        "run": generate_quiz,
        "args_model": GenerateQuizArgs,
    },
    "generate_study_plan": {
        "signature": '(confirmed?: bool)',
        "description": "MUTATING: regenerate the study plan. Propose first, execute when confirmed=true.",
        "parameters": {"type": "object", "properties": {"confirmed": {"type": "boolean"}}},
        "run": generate_study_plan,
    },
    "log_study": {
        "signature": '(topic_id: int, minutes_spent: int, confirmed?: bool)',
        "description": "MUTATING: log a study session. Propose first, execute when confirmed=true.",
        "parameters": {"type": "object", "properties": {"topic_id": {"type": "integer"}, "minutes_spent": {"type": "integer"}, "confirmed": {"type": "boolean"}}, "required": ["topic_id", "minutes_spent"]},
        "run": log_study,
    },
    "create_deadline": {
        "signature": '(course_id: int, title: str, due_date: str YYYY-MM-DD, weight?: float, topic_id?: int, confirmed?: bool)',
        "description": "MUTATING: add a deadline. Propose first, execute when confirmed=true.",
        "parameters": {"type": "object", "properties": {"course_id": {"type": "integer"}, "title": {"type": "string"}, "due_date": {"type": "string"}, "weight": {"type": "number"}, "topic_id": {"type": "integer"}, "confirmed": {"type": "boolean"}}, "required": ["course_id", "title", "due_date"]},
        "run": create_deadline,
    },
    "take_passage_note": {
        "signature": '(passage_id: int, note: str, confirmed?: bool)',
        "description": (
            "MUTATING: pin an annotation to a passage (clarify a confusing "
            "sentence, link related concepts, warn about a misconception). "
            "Call first with confirmed omitted/false to propose; re-call with "
            "confirmed=true only after the student says yes."
        ),
        "parameters": {"type": "object", "properties": {"passage_id": {"type": "integer"}, "note": {"type": "string"}, "confirmed": {"type": "boolean"}}, "required": ["passage_id", "note"]},
        "run": take_passage_note,
    },
    "ask_clarify": {
        "signature": '(question: str, options?: str[], allow_free_text?: bool)',
        "description": (
            "Ask a disambiguating question — renders INLINE as a tappable "
            "selection card (options) plus optional free-text answer. Use when "
            "the request is ambiguous: which topic, what depth, which exam, "
            "what the learner already knows. Max 4 short options. No "
            "confirmation needed; never use for quiz questions (use "
            "generate_quiz) or confirmations of mutations."
        ),
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}, "allow_free_text": {"type": "boolean"}}, "required": ["question"]},
        "run": ask_clarify,
        "args_model": AskClarifyArgs,
    },
    "record_understanding": {
        "signature": '(topic_id: int, demonstrated: float, coverage?: float, evidence?: str)',
        "description": (
            "Record understanding the learner demonstrated IN CHAT: a correct "
            "explanation, an accurate paraphrase, a right answer to a check "
            "question. demonstrated is 0.0-1.0 for how correct they were ON "
            "WHAT WAS TESTED; coverage is 0.0-1.0 for what fraction of the "
            "WHOLE topic that evidence spans (one subtopic of five ≈ 0.2, a "
            "single check question ≈ 0.1-0.3, a full-topic explanation ≈ "
            "0.8-1.0). The score update is scaled by coverage, so partial "
            "evidence nudges instead of jumping. With an active plan, use the "
            "finished step's weight as coverage. Estimate coverage every "
            "call. evidence is a short quote of what they got right. "
            "Background write — no confirmation, never mention scores. Call "
            "it in the same turn you praise/confirm their answer."
        ),
        "parameters": {"type": "object", "properties": {"topic_id": {"type": "integer"}, "demonstrated": {"type": "number"}, "coverage": {"type": "number", "description": "REQUIRED: what fraction of the WHOLE topic was tested (count the topic's subtopics: one of five = 0.2, single check question = 0.1-0.3, full-topic explanation = 0.8-1.0)"}, "evidence": {"type": "string"}}, "required": ["topic_id", "demonstrated", "coverage"]},
        "run": record_understanding,
        "args_model": RecordUnderstandingArgs,
    },
    "ask_review": {
        "signature": '(items: {topic_id: int, prompt: str, key_points: str[]}[])',
        "description": (
            "Run a spaced-repetition recall session — renders INLINE as flip "
            "cards (prompt → reveal → self-rate Forgot/Shaky/Knew, graded "
            "straight into SM-2). Build ONE item per due topic from "
            "get_due_reviews, with prompt + key points grounded in that "
            "topic's passages (use get_passages first). Capped at the user's "
            "review batch setting. No "
            "confirmation needed; never use for new teaching (that's chat) "
            "or graded quizzes (that's generate_quiz)."
        ),
        "parameters": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object"}}}, "required": ["items"]},
        "run": ask_review,
        "args_model": AskReviewArgs,
    },
    "start_timer": {
        "signature": '(topic_id: int, label?: str)',
        "description": (
            "Start a study timer on a topic — renders as a live pill in the "
            "tutor header; stopping auto-logs the session (study log + SM-2 "
            "tick). Call when the learner begins focused study ('let me study "
            "X', starting a plan item). No confirmation needed."
        ),
        "parameters": {"type": "object", "properties": {"topic_id": {"type": "integer"}, "label": {"type": "string"}}, "required": ["topic_id"]},
        "run": start_timer,
        "args_model": StartTimerArgs,
    },
    "stop_timer": {
        "signature": '()',
        "description": (
            "Stop the active study timer ('I'm done', 'stop the timer'). The "
            "frontend logs the elapsed session automatically. No confirmation."
        ),
        "parameters": {"type": "object", "properties": {}},
        "run": stop_timer,
    },
    "update_todo": {
        "signature": '(todos: {content: str, status: str, activeForm?: str, weight?: float}[])',
        "description": (
            "Standard plan tracker for multi-step work — renders as a progress "
            "graph in the side panel. Pass the FULL list each call "
            "(status: pending | in_progress | completed, exactly ONE "
            "in_progress). content is the step name; activeForm is the "
            "present-continuous label ('Building quiz'). For topic study, "
            "open the plan at session start with one step per subtopic and a "
            "weight per step (share of the whole topic; normalized to sum "
            "1.0, equal splits if omitted) — then score each finished "
            "subtopic with record_understanding using coverage = its weight, "
            "so the topic score is the fair sum of weight × demonstrated. "
            "No confirmation needed; never paste the list in text."
        ),
        "parameters": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object"}}}, "required": ["todos"]},
        "run": update_todo,
        "args_model": UpdateTodoArgs,
    },
}


def run_tool(db, user_id: int, name: str, args: dict) -> Any:
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"unknown tool '{name}'"}
    args = args or {}
    model = spec.get("args_model")
    if model is not None:
        try:
            # exclude_none: an explicit null must fall back to the function's
            # own default (int(None) would crash where a missing key works).
            args = model.model_validate(args).model_dump(exclude_none=True)
        except Exception as e:  # noqa: BLE001 — ValidationError -> model-readable
            return {"error": f"invalid args for '{name}': {e}"[:500]}
    return spec["run"](db, user_id, args)


def openai_tools() -> list[dict]:
    """TOOLS registry rendered as OpenAI function schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{spec['signature']}: {spec['description']}",
                "parameters": spec["parameters"],
            },
        }
        for name, spec in TOOLS.items()
    ]
