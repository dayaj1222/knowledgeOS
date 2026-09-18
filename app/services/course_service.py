"""Course hierarchy service: navigation, counts, cascades.

Owns everything about the Course -> Module -> Topic spine so routers stay
thin (validate -> call service -> return) and future features (e.g. cloning
a course, reordering modules) land here without touching HTTP code.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ._helpers import get_or_404


class CourseService:
    @staticmethod
    def require_user_course(db: Session, user_id: int, course_id: int) -> models.Course:
        """Return a course only when it belongs to the declared user.

        This is deliberately a 404 rather than a 403: callers must not learn
        that another user's object exists from a guessed numeric identifier.
        """
        course = db.scalar(
            select(models.Course).where(
                models.Course.id == course_id, models.Course.user_id == user_id
            )
        )
        if course is None:
            from fastapi import HTTPException

            raise HTTPException(404, "Course not found")
        return course

    @staticmethod
    def require_user_module(db: Session, user_id: int, module_id: int) -> models.Module:
        module = db.scalar(
            select(models.Module)
            .join(models.Course, models.Module.course_id == models.Course.id)
            .where(models.Module.id == module_id, models.Course.user_id == user_id)
        )
        if module is None:
            from fastapi import HTTPException

            raise HTTPException(404, "Module not found")
        return module

    @staticmethod
    def require_user_topic(db: Session, user_id: int, topic_id: int) -> models.Topic:
        topic = db.scalar(
            select(models.Topic)
            .join(models.Module, models.Topic.module_id == models.Module.id)
            .join(models.Course, models.Module.course_id == models.Course.id)
            .where(models.Topic.id == topic_id, models.Course.user_id == user_id)
        )
        if topic is None:
            from fastapi import HTTPException

            raise HTTPException(404, "Topic not found")
        return topic

    @staticmethod
    def require_course(db: Session, course_id: int) -> models.Course:
        return get_or_404(db, models.Course, course_id, "Course not found")

    @staticmethod
    def require_module(db: Session, module_id: int) -> models.Module:
        return get_or_404(db, models.Module, module_id, "Module not found")

    @staticmethod
    def require_topic(db: Session, topic_id: int) -> models.Topic:
        return get_or_404(db, models.Topic, topic_id, "Topic not found")

    @staticmethod
    def passage_counts(db: Session, topic_ids: list[int]) -> dict[int, int]:
        """Map topic_id -> chunks in the topic's module pool (shared pool:
        siblings report the same number — the pool belongs to the module)."""
        if not topic_ids:
            return {}
        from .retrieval import pool_counts

        topics = db.scalars(
            select(models.Topic).where(models.Topic.id.in_(topic_ids))
        ).all()
        counts = pool_counts(db, [t.module_id for t in topics if t.module_id is not None])
        return {
            t.id: counts.get(t.module_id, 0)
            for t in topics
            if t.module_id is not None
        }

    @staticmethod
    def course_counts(db: Session, course_ids: list[int]) -> dict[int, dict]:
        """Map course_id -> {module_count, topic_count} (two grouped queries)."""
        if not course_ids:
            return {}
        mod_rows = db.execute(
            select(models.Module.course_id, func.count(models.Module.id))
            .where(models.Module.course_id.in_(course_ids))
            .group_by(models.Module.course_id)
        ).all()
        topic_rows = db.execute(
            select(models.Module.course_id, func.count(models.Topic.id))
            .join(models.Topic, models.Topic.module_id == models.Module.id)
            .where(models.Module.course_id.in_(course_ids))
            .group_by(models.Module.course_id)
        ).all()
        out = {cid: {"module_count": 0, "topic_count": 0} for cid in course_ids}
        for cid, n in mod_rows:
            out[cid]["module_count"] = n
        for cid, n in topic_rows:
            out[cid]["topic_count"] = n
        return out

    @staticmethod
    def delete_course(db: Session, course_id: int) -> None:
        """Cascade-delete a course and everything under it."""
        course = CourseService.require_course(db, course_id)
        for module in list(course.modules):
            CourseService.delete_module(db, module.id)
        for res in list(course.resources):
            for p in list(res.passages):
                db.delete(p)
            db.delete(res)
        for dl in list(course.deadlines):
            db.delete(dl)
        db.delete(course)
        db.commit()

    @staticmethod
    def delete_module(db: Session, module_id: int) -> None:
        """Cascade-delete a module, its topics, and topic-scoped rows."""
        module = CourseService.require_module(db, module_id)
        for topic in list(module.topics):
            CourseService.delete_topic(db, topic.id, force=True, commit=False)
        # passages tagged to this module's resource stay, but clear module link
        for res in db.scalars(
            select(models.Resource).where(models.Resource.module_id == module_id)
        ).all():
            res.module_id = None
        db.delete(module)
        db.commit()

    @staticmethod
    def delete_topic(
        db: Session, topic_id: int, *, force: bool = False, commit: bool = True
    ) -> None:
        """Delete a topic; blocks when downstream data exists unless forced."""
        topic = CourseService.require_topic(db, topic_id)
        has_children = any(
            [
                db.scalar(
                    select(models.Question.id).where(
                        models.Question.topic_id == topic_id
                    )
                ),
                db.scalar(
                    select(models.Review.id).where(models.Review.topic_id == topic_id)
                ),
            ]
        )
        if has_children and not force:
            from fastapi import HTTPException

            raise HTTPException(
                409,
                "Topic has questions/reviews; use ?force=true to cascade",
            )
        db.query(models.Question).filter(
            models.Question.topic_id == topic_id
        ).delete()
        db.query(models.Review).filter(models.Review.topic_id == topic_id).delete()
        # Passages are module-scoped (module-pool RAG), never filed under
        # topics — deleting a topic touches no passages.
        db.query(models.Proficiency).filter(
            models.Proficiency.topic_id == topic_id
        ).delete()
        db.delete(topic)
        if commit:
            db.commit()
