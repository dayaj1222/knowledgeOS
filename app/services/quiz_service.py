"""Quiz service: question synthesis, rubric grading, proficiency write-back.

The question -> answer loop writes back to Proficiency: a low-scored attempt
lowers it, a high score raises it (exponential running average). Malformed
questions are flagged via Attempt.excluded so they stop being evaluated.

Grading prefers the LLM (full context: question + grounding passages +
known weaknesses) and degrades to deterministic keyword overlap when the
LLM is unavailable — so grading never hard-fails.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..agent import (
    aevaluate_answer as a_agent_evaluate_answer,
    agenerate_questions as a_agent_generate_questions,
    evaluate_answer as agent_evaluate_answer,
    generate_questions as agent_generate_questions,
)

ALPHA = 0.3  # proficiency running-average weight for each new attempt


class QuizService:
    # ---- proficiency write-back ----
    @staticmethod
    def fold_attempt_into_proficiency(
        db: Session, attempt: models.Attempt, topic_id: int
    ) -> None:
        prof = db.scalar(
            select(models.Proficiency).where(
                models.Proficiency.user_id == attempt.user_id,
                models.Proficiency.topic_id == topic_id,
            )
        )
        if prof is None:
            prof = models.Proficiency(
                user_id=attempt.user_id, topic_id=topic_id, score=attempt.score
            )
            db.add(prof)
        else:
            prof.score = (1 - ALPHA) * prof.score + ALPHA * attempt.score
            db.add(prof)

    # ---- question synthesis ----
    @staticmethod
    def _grounding_passages(db: Session, topic_id: int) -> list[str]:
        passages = db.scalars(
            select(models.Passage).where(models.Passage.topic_id == topic_id)
        ).all()
        return [p.content for p in passages]

    @staticmethod
    def generate_for_topic(
        db: Session,
        topic: models.Topic,
        count: int,
        *,
        difficulty: str = "medium",
        instructions: str = "",
    ) -> list[models.Question]:
        generated = agent_generate_questions(
            topic.name,
            QuizService._grounding_passages(db, topic.id),
            count,
            difficulty=difficulty,
            instructions=instructions,
        )
        out = []
        for g in generated.questions:
            q = models.Question(
                topic_id=topic.id,
                text=g.text,
                type=g.type,
                expected_key_points=g.expected_key_points,
                generated_by="EXPERT",
            )
            db.add(q)
            out.append(q)
        return out

    @staticmethod
    def generate_quiz(
        db: Session,
        topic_ids: list[int],
        questions_per_topic: int = 3,
        difficulty: str = "medium",
        instructions: str = "",
    ) -> list[models.Question]:
        """Generate + stage (not yet committed) questions for multiple topics.

        Questions are a permanent DB addition once committed by the caller;
        the frontend then offers a "Take quiz" step without regenerating.
        """
        created: list[models.Question] = []
        for topic_id in topic_ids:
            topic = db.get(models.Topic, topic_id)
            if topic is None:
                continue
            created.extend(
                QuizService.generate_for_topic(
                    db,
                    topic,
                    questions_per_topic,
                    difficulty=difficulty,
                    instructions=instructions,
                )
            )
        db.commit()
        for q in created:
            db.refresh(q)
        return created

    # ---- async variants (tutor path: safe inside a running event loop) ----

    @staticmethod
    async def agenerate_for_topic(
        db: Session,
        topic: models.Topic,
        count: int,
        *,
        difficulty: str = "medium",
        instructions: str = "",
    ) -> list[models.Question]:
        """Async twin of generate_for_topic (LLM call awaited, no nested loop)."""
        generated = await a_agent_generate_questions(
            topic.name,
            QuizService._grounding_passages(db, topic.id),
            count,
            difficulty=difficulty,
            instructions=instructions,
        )
        out = []
        for g in generated.questions:
            q = models.Question(
                topic_id=topic.id,
                text=g.text,
                type=g.type,
                expected_key_points=g.expected_key_points,
                generated_by="EXPERT",
            )
            db.add(q)
            out.append(q)
        return out

    @staticmethod
    async def agenerate_quiz(
        db: Session,
        user_id: int,
        topic_ids: list[int],
        questions_per_topic: int = 3,
        difficulty: str = "medium",
        instructions: str = "",
    ) -> tuple[models.Assessment, list[models.Question]]:
        """Generate questions AND a first-class Assessment session grouping them.

        Unlike generate_quiz (loose per-topic rows for the manual flow), this
        creates Assessment(status="ready") + AssessmentQuestion links so the
        quiz is deep-linkable (/quiz/take/:id), refresh-safe, and submittable
        against its own session instead of a lazily created one.
        """
        assessment = models.Assessment(user_id=user_id, status="ready")
        db.add(assessment)
        db.flush()  # id for the links below
        created: list[models.Question] = []
        for topic_id in topic_ids:
            topic = db.get(models.Topic, topic_id)
            if topic is None:
                continue
            created.extend(
                await QuizService.agenerate_for_topic(
                    db, topic, questions_per_topic,
                    difficulty=difficulty, instructions=instructions,
                )
            )
        db.flush()  # question ids for the links below
        for order, q in enumerate(created):
            db.add(
                models.AssessmentQuestion(
                    assessment_id=assessment.id,
                    question_id=q.id,
                    order_index=order,
                )
            )
        db.commit()
        db.refresh(assessment)
        for q in created:
            db.refresh(q)
        return assessment, created

    @staticmethod
    async def agenerate_drill(
        db: Session,
        user_id: int,
        *,
        topic_id: int | None = None,
        count: int = 5,
        difficulty: str = "medium",
    ) -> tuple[models.Assessment, list[models.Question]]:
        """Async twin of generate_drill that also mints an Assessment session."""
        weaknesses = {
            w["topic_id"]: w for w in QuizService.topic_weaknesses(db, user_id)
        }
        if topic_id is not None:
            targets = [topic_id]
        elif weaknesses:
            targets = list(weaknesses)[:3]
        else:
            profs = db.scalars(
                select(models.Proficiency)
                .where(models.Proficiency.user_id == user_id)
                .order_by(models.Proficiency.score)
                .limit(3)
            ).all()
            targets = [p.topic_id for p in profs]
            if not targets:
                topics = db.scalars(select(models.Topic).limit(3)).all()
                targets = [t.id for t in topics]

        assessment = models.Assessment(user_id=user_id, status="ready")
        db.add(assessment)
        db.flush()
        created: list[models.Question] = []
        per_topic, remainder = divmod(max(count, 1), max(len(targets), 1))
        for i, tid in enumerate(targets):
            topic = db.get(models.Topic, tid)
            if topic is None:
                continue
            gaps = [m["point"] for m in weaknesses.get(tid, {}).get("missed", [])]
            instructions = (
                f"Drill the learner's known gaps: {'; '.join(gaps)}. "
                "Every question must test at least one of these gaps."
                if gaps
                else "Focus on foundational understanding of this topic."
            )
            created.extend(
                await QuizService.agenerate_for_topic(
                    db, topic, per_topic + (1 if i < remainder else 0),
                    difficulty=difficulty, instructions=instructions,
                )
            )
        db.flush()  # question ids for the links below
        for order, q in enumerate(created):
            db.add(
                models.AssessmentQuestion(
                    assessment_id=assessment.id,
                    question_id=q.id,
                    order_index=order,
                )
            )
        db.commit()
        db.refresh(assessment)
        for q in created:
            db.refresh(q)
        return assessment, created

    # ---- grading ----
    @staticmethod
    def keyword_grade(
        question: models.Question, user_answer: str
    ) -> tuple[float, str, list[str], list[str]]:
        """Score by keyword overlap; returns (score, feedback, matched, missed)."""
        key_points = [str(k) for k in (question.expected_key_points or [])]
        if not key_points:
            return (
                (1.0 if user_answer.strip() else 0.0),
                "No answer key; scored by presence.",
                [],
                [],
            )
        answer_lower = user_answer.lower()
        matched = [k for k in key_points if k.lower() in answer_lower]
        missed = [k for k in key_points if k not in matched]
        score = round(len(matched) / len(key_points), 2)
        feedback = (
            f"Matched {len(matched)}/{len(key_points)} key points."
            if matched
            else "No key points matched."
        )
        return score, feedback, matched, missed

    @staticmethod
    async def agrade_answer(
        db: Session, question: models.Question, user_answer: str
    ) -> tuple[float, str, list[str], list[str]]:
        """Grade via the LLM (awaited — safe inside a running event loop).

        Sends the question + its relevant passage content + your answer; the
        model scores 0.0–1.0 by meaning (paraphrases count) with feedback and
        matched/missed key points. Falls back to keyword overlap only if the
        LLM itself fails.
        """
        try:
            prof = db.scalar(
                select(models.Proficiency).where(
                    models.Proficiency.topic_id == question.topic_id
                )
            )
            weaknesses = (prof.weak_points if prof else []) or []
            eval_ = await a_agent_evaluate_answer(
                question.text,
                question.expected_key_points or [],
                user_answer,
                passages=QuizService._grounding_passages(db, question.topic_id),
                weaknesses=weaknesses,
            )
            return (
                eval_.score,
                eval_.feedback or "Graded.",
                eval_.matched_key_points,
                eval_.missed_key_points,
            )
        except Exception:  # noqa: BLE001 — LLM down; degrade to keyword match
            return QuizService.keyword_grade(question, user_answer)

    @staticmethod
    def grade_answer(
        db: Session, question: models.Question, user_answer: str
    ) -> tuple[float, str, list[str], list[str]]:
        """Grade via the LLM with full context; fall back to keyword overlap."""
        try:
            prof = db.scalar(
                select(models.Proficiency).where(
                    models.Proficiency.topic_id == question.topic_id
                )
            )
            weaknesses = (prof.weak_points if prof else []) or []
            eval_ = agent_evaluate_answer(
                question.text,
                question.expected_key_points or [],
                user_answer,
                passages=QuizService._grounding_passages(db, question.topic_id),
                weaknesses=weaknesses,
            )
            return (
                eval_.score,
                eval_.feedback or "Graded.",
                eval_.matched_key_points,
                eval_.missed_key_points,
            )
        except Exception:  # noqa: BLE001 — LLM down; degrade to keyword match
            return QuizService.keyword_grade(question, user_answer)

    # ---- weakness diagnosis + targeted drills ----
    @staticmethod
    def topic_weaknesses(
        db: Session, user_id: int, *, top_points: int = 5
    ) -> list[dict]:
        """Aggregate missed_key_points across the user's graded attempts.

        Returns per-topic rows sorted by total misses:
        {topic_id, topic_name, score, total_missed, missed: [{point, count}]}.
        Excluded (malformed-question) attempts never count.
        """
        attempts = db.scalars(
            select(models.Attempt).where(
                models.Attempt.user_id == user_id,
                models.Attempt.excluded.is_(False),
            )
        ).all()
        if not attempts:
            return []

        qids = {a.question_id for a in attempts}
        questions = {
            q.id: q
            for q in db.scalars(
                select(models.Question).where(models.Question.id.in_(qids))
            ).all()
        }
        profs = {
            p.topic_id: p.score
            for p in db.scalars(
                select(models.Proficiency).where(
                    models.Proficiency.user_id == user_id
                )
            ).all()
        }

        from collections import Counter

        misses: dict[int, Counter] = {}
        for a in attempts:
            q = questions.get(a.question_id)
            if q is None:
                continue
            for point in a.missed_key_points or []:
                misses.setdefault(q.topic_id, Counter())[str(point)] += 1

        rows = []
        for topic_id, counter in sorted(
            misses.items(), key=lambda kv: -sum(kv[1].values())
        ):
            topic = db.get(models.Topic, topic_id)
            rows.append(
                {
                    "topic_id": topic_id,
                    "topic_name": topic.name if topic else f"Topic #{topic_id}",
                    "score": profs.get(topic_id, 0.0),
                    "total_missed": sum(counter.values()),
                    "missed": [
                        {"point": p, "count": c}
                        for p, c in counter.most_common(top_points)
                    ],
                }
            )
        return rows

    # ---- per-answer detail (tutor misconception diagnosis) ----
    @staticmethod
    def recent_attempts(
        db: Session, user_id: int, *, topic_id: int | None = None, limit: int = 8
    ) -> list[dict]:
        """Newest graded attempts with full per-question detail.

        Each row: {attempt_id, assessment_id, question_id, topic_id,
        topic_name, question_text, question_type, expected_key_points,
        user_answer, score, feedback, matched_key_points, missed_key_points}.
        Excluded (malformed-question) attempts are skipped. Newest first.
        """
        limit = max(1, min(int(limit or 8), 25))
        attempts = db.scalars(
            select(models.Attempt)
            .where(
                models.Attempt.user_id == user_id,
                models.Attempt.excluded.is_(False),
            )
            .order_by(models.Attempt.id.desc())
            .limit(limit * 4)  # over-fetch; topic filter applies below
        ).all()
        if not attempts:
            return []

        qids = {a.question_id for a in attempts}
        questions = {
            q.id: q
            for q in db.scalars(
                select(models.Question).where(models.Question.id.in_(qids))
            ).all()
        }
        tids = {q.topic_id for q in questions.values()}
        names = {
            t.id: t.name
            for t in db.scalars(
                select(models.Topic).where(models.Topic.id.in_(tids))
            ).all()
        } if tids else {}

        rows = []
        for a in attempts:
            q = questions.get(a.question_id)
            if q is None:
                continue
            if topic_id is not None and q.topic_id != topic_id:
                continue
            rows.append({
                "attempt_id": a.id,
                "assessment_id": a.assessment_id,
                "question_id": q.id,
                "topic_id": q.topic_id,
                "topic_name": names.get(q.topic_id, f"Topic #{q.topic_id}"),
                "question_text": q.text,
                "question_type": q.type,
                "expected_key_points": q.expected_key_points or [],
                "user_answer": a.user_answer or "",
                "score": a.score,
                "feedback": a.feedback or "",
                "matched_key_points": a.matched_key_points or [],
                "missed_key_points": a.missed_key_points or [],
            })
            if len(rows) >= limit:
                break
        return rows

    @staticmethod
    def sync_weak_points(
        db: Session, *, user_id: int, topic_id: int, limit: int = 8
    ) -> None:
        """Refresh Proficiency.weak_points from aggregated misses (no commit).

        Computed gaps go first; any manually recorded entries are kept after,
        de-duplicated — so the diagnosis loop never clobbers a manual override.
        """
        # SessionLocal runs with autoflush=False: flush first so the lookup
        # below sees a proficiency row created earlier in the same session
        # (e.g. by fold_attempt_into_proficiency during grading).
        db.flush()
        for row in QuizService.topic_weaknesses(db, user_id):
            if row["topic_id"] != topic_id:
                continue
            prof = db.scalar(
                select(models.Proficiency).where(
                    models.Proficiency.user_id == user_id,
                    models.Proficiency.topic_id == topic_id,
                )
            )
            if prof is None:
                return
            computed = [m["point"] for m in row["missed"]]
            manual = [w for w in (prof.weak_points or []) if w not in computed]
            prof.weak_points = (computed + manual)[:limit]
            db.add(prof)
            return

    @staticmethod
    def generate_drill(
        db: Session,
        user_id: int,
        *,
        topic_id: int | None = None,
        count: int = 5,
        difficulty: str = "medium",
    ) -> list[models.Question]:
        """Generate questions aimed at the learner's known gaps.

        Targets one topic (or the weakest topics by miss count), grounding
        each generation pass in that topic's top-missed key points so the
        questions drill exactly what the learner keeps getting wrong.
        Cold start (no misses yet): falls back to lowest-proficiency topics.
        """
        weaknesses = {
            w["topic_id"]: w for w in QuizService.topic_weaknesses(db, user_id)
        }

        if topic_id is not None:
            targets = [topic_id]
        elif weaknesses:
            targets = list(weaknesses)[:3]
        else:
            profs = db.scalars(
                select(models.Proficiency)
                .where(models.Proficiency.user_id == user_id)
                .order_by(models.Proficiency.score)
                .limit(3)
            ).all()
            targets = [p.topic_id for p in profs]
            if not targets:
                topics = db.scalars(select(models.Topic).limit(3)).all()
                targets = [t.id for t in topics]

        created: list[models.Question] = []
        per_topic, remainder = divmod(max(count, 1), max(len(targets), 1))
        for i, tid in enumerate(targets):
            topic = db.get(models.Topic, tid)
            if topic is None:
                continue
            gaps = [m["point"] for m in weaknesses.get(tid, {}).get("missed", [])]
            instructions = (
                f"Drill the learner's known gaps: {'; '.join(gaps)}. "
                "Every question must test at least one of these gaps."
                if gaps
                else "Focus on foundational understanding of this topic."
            )
            created.extend(
                QuizService.generate_for_topic(
                    db,
                    topic,
                    per_topic + (1 if i < remainder else 0),
                    difficulty=difficulty,
                    instructions=instructions,
                )
            )
        db.commit()
        for q in created:
            db.refresh(q)
        return created
