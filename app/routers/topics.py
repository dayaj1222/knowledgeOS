"""Topic + Proficiency + Preference endpoints (standard envelope)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..protocol import ok
from ..services.course_service import CourseService
from ..services.proficiency_service import MANUAL_OVERRIDE, ProficiencyService

router = APIRouter(prefix="/api", tags=["topics"])


def _dump(schema_cls, obj):
    return schema_cls.model_validate(obj).model_dump(mode="json")


# ---- Topics ----
@router.post("/topics", status_code=201)
def create_topic(payload: schemas.TopicCreate, db: Session = Depends(get_db)):
    if not db.get(models.Module, payload.module_id):
        from fastapi import HTTPException

        raise HTTPException(404, "Module not found")
    topic = models.Topic(**payload.model_dump())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return ok(_dump(schemas.TopicOut, topic))


@router.get("/modules/{module_id}/topics")
def list_topics(module_id: int, db: Session = Depends(get_db)):
    topics = db.scalars(
        select(models.Topic)
        .where(models.Topic.module_id == module_id)
        .order_by(models.Topic.order_index)
    ).all()
    counts = CourseService.passage_counts(db, [t.id for t in topics])
    return ok([
        {
            **_dump(schemas.TopicOut, t),
            "passage_count": counts.get(t.id, 0),
        }
        for t in topics
    ])


@router.get("/topics/{topic_id}")
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = CourseService.require_topic(db, topic_id)
    return ok(_dump(schemas.TopicOut, topic))


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: int, payload: schemas.TopicUpdate, db: Session = Depends(get_db)):
    topic = CourseService.require_topic(db, topic_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(topic, k, v)
    db.commit()
    db.refresh(topic)
    return ok(_dump(schemas.TopicOut, topic))


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, force: bool = False, db: Session = Depends(get_db)):
    CourseService.delete_topic(db, topic_id, force=force)
    return ok({"deleted": True, "id": topic_id})


# ---- Proficiency ----
@router.get("/users/{user_id}/proficiency")
def list_proficiency(user_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(models.Proficiency).where(models.Proficiency.user_id == user_id)
    ).all()
    return ok([_dump(schemas.ProficiencyOut, p) for p in rows])


@router.put("/users/{user_id}/proficiency/{topic_id}")
def upsert_proficiency(
    user_id: int, topic_id: int, payload: schemas.ProficiencyUpdate, db: Session = Depends(get_db)
):
    data = payload.model_dump(exclude_unset=True)
    prof = None
    if "score" in data and data["score"] is not None:
        # Manual override sets the score exactly (alpha=1) and ledgers it.
        # Use the returned row directly: autoflush is OFF, so re-querying
        # would miss the pending insert and double-create (unique clash).
        prof, _ = ProficiencyService.record(
            db,
            user_id=user_id,
            topic_id=topic_id,
            observed=data.pop("score"),
            alpha=1.0,
            source=MANUAL_OVERRIDE,
        )
    if prof is None:
        prof = db.scalar(
            select(models.Proficiency).where(
                models.Proficiency.user_id == user_id,
                models.Proficiency.topic_id == topic_id,
            )
        )
    if prof is None:
        prof = models.Proficiency(user_id=user_id, topic_id=topic_id)
        db.add(prof)
    for k, v in data.items():
        if v is not None:
            setattr(prof, k, v)
    db.commit()
    db.refresh(prof)
    return ok(_dump(schemas.ProficiencyOut, prof))


# ---- Preference ----
@router.get("/users/{user_id}/preference")
def get_preference(user_id: int, db: Session = Depends(get_db)):
    pref = db.scalar(
        select(models.Preference).where(models.Preference.user_id == user_id)
    )
    if not pref:
        from fastapi import HTTPException

        raise HTTPException(404, "Preference not found")
    return ok(_dump(schemas.PreferenceOut, pref))


@router.get("/users/{user_id}/system-prompt")
def get_system_prompt(user_id: int, db: Session = Depends(get_db)):
    """Return the ACTUAL tutor system prompt for this user.

    Single source of truth: assembled by prompt.build_system_prompt from the
    saved Preference (style/verbosity/instructions). What this returns is
    what the model receives as the `system` message (before the static
    library structure, which is per-conversation and appended at runtime).
    """
    from ..agent.prompt import build_system_prompt

    pref = db.scalar(
        select(models.Preference).where(models.Preference.user_id == user_id)
    )
    prompt = build_system_prompt(
        style=getattr(pref, "tutor_style", None),
        verbosity=getattr(pref, "tutor_verbosity", None),
        instructions=getattr(pref, "tutor_instructions", None),
    )
    return ok({"system_prompt": prompt})


@router.put("/users/{user_id}/preference")
def upsert_preference(
    user_id: int, payload: schemas.PreferenceUpdate, db: Session = Depends(get_db)
):
    from fastapi import HTTPException

    data = payload.model_dump(exclude_unset=True)
    _enums = {
        "tutor_style": {"socratic", "balanced", "direct", "drill"},
        "tutor_verbosity": {"concise", "balanced", "detailed"},
        "default_difficulty": {"easy", "medium", "hard"},
    }
    for k, allowed in _enums.items():
        if data.get(k) is not None and data[k] not in allowed:
            raise HTTPException(400, f"{k} must be one of {sorted(allowed)}")
    if data.get("default_quiz_count") is not None and not 1 <= data["default_quiz_count"] <= 10:
        raise HTTPException(400, "default_quiz_count must be 1-10")
    if data.get("review_batch_size") is not None and not 1 <= data["review_batch_size"] <= 15:
        raise HTTPException(400, "review_batch_size must be 1-15")
    pref = db.scalar(
        select(models.Preference).where(models.Preference.user_id == user_id)
    )
    if not pref:
        pref = models.Preference(user_id=user_id)
        db.add(pref)
    for k, v in data.items():
        if v is not None:
            setattr(pref, k, v)
    db.commit()
    db.refresh(pref)
    return ok(_dump(schemas.PreferenceOut, pref))
