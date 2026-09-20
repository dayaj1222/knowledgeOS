"""SQLAlchemy models for the AI study knowledge base.

Schema decisions applied (from review):
- Module is a SEPARATE table (syllabus-aligned), not a root Topic.
- StudyLog captures the knowledge -> proficiency loop (study events, not just quizzes).
- Passage grounding is by topic_id (plain SQL), set by the tagger at upload.
  No vector index: categorization already answers "which passages belong here".
- Slot.type is `free | class | busy` (no `fixed` overlap).
- Plan has a status column so stale plans can be superseded.
- Attempt.excluded flags malformed questions; low scores write back to Proficiency.
"""

from __future__ import annotations

from datetime import datetime, time
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    college: Mapped[str | None] = mapped_column(String(255))
    course_name: Mapped[str] = mapped_column(String(255), default="B.Tech CSE")
    semester: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(255))

    courses: Mapped[list[Course]] = relationship(back_populates="user")
    proficiency: Mapped[list[Proficiency]] = relationship(back_populates="user")
    preference: Mapped[Preference | None] = relationship(back_populates="user", uselist=False)


class Course(Base, TimestampMixin):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="ETH")  # TH | ETH | ELA
    instructor: Mapped[str | None] = mapped_column(String(255))
    credits: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(
        String(16), default="not_started"
    )  # not_started | in_progress | completed
    color: Mapped[str | None] = mapped_column(String(16))

    user: Mapped[User] = relationship(back_populates="courses")
    modules: Mapped[list[Module]] = relationship(back_populates="course")
    resources: Mapped[list[Resource]] = relationship(back_populates="course")
    deadlines: Mapped[list[Deadline]] = relationship(back_populates="course")


class Module(Base, TimestampMixin):
    """A syllabus unit grouping topics. CATs/exams are scoped to modules."""

    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped[Course] = relationship(back_populates="modules")
    topics: Mapped[list[Topic]] = relationship(back_populates="module")


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), nullable=False)
    parent_topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)  # query side for matching
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1-5 exam importance
    prerequisite_ids: Mapped[list] = mapped_column(JSON, default=list)

    module: Mapped[Module] = relationship(back_populates="topics")
    children: Mapped[list[Topic]] = relationship(
        back_populates="parent", remote_side=[id]
    )
    parent: Mapped[Topic | None] = relationship(
        back_populates="children", remote_side=[parent_topic_id]
    )
    questions: Mapped[list[Question]] = relationship(back_populates="topic")
    proficiency: Mapped[list[Proficiency]] = relationship(back_populates="topic")
    reviews: Mapped[list[Review]] = relationship(back_populates="topic")


class Proficiency(Base, TimestampMixin):
    __tablename__ = "proficiency"
    __table_args__ = (UniqueConstraint("user_id", "topic_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0-1.0
    weak_points: Mapped[list] = mapped_column(JSON, default=list)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    preferred_method: Mapped[str] = mapped_column(
        String(16), default="mixed"
    )  # visual | reading | practice | mixed
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="proficiency")
    topic: Mapped[Topic] = relationship(back_populates="proficiency")


class Resource(Base, TimestampMixin):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="pdf")  # pdf | slides | notes
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="uploaded"
    )  # uploaded | processing | done | partial | failed
    error: Mapped[str | None] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    course: Mapped[Course] = relationship(back_populates="resources")
    passages: Mapped[list[Passage]] = relationship(back_populates="resource")


class ExtractionJob(Base, TimestampMixin):
    """Durable local work queue entry for resource extraction."""

    __tablename__ = "extraction_jobs"
    __table_args__ = (UniqueConstraint("resource_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Passage(Base):
    __tablename__ = "passages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    index_order: Mapped[int] = mapped_column(Integer, default=0)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    section_path: Mapped[str | None] = mapped_column(String(512))  # "A > B" headings
    tag_confidence: Mapped[float | None] = mapped_column(Float)  # deterministic tag score
    extra_topic_ids: Mapped[list] = mapped_column(JSON, default=list)  # runners-up
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    resource: Mapped[Resource] = relationship(back_populates="passages")
    question_links: Mapped[list[QuestionPassage]] = relationship(
        back_populates="passage"
    )
    notes: Mapped[list[PassageNote]] = relationship(
        back_populates="passage", cascade="all, delete-orphan"
    )
    embedding: Mapped[PassageEmbedding | None] = relationship(
        back_populates="passage", cascade="all, delete-orphan", uselist=False
    )


class PassageEmbedding(Base):
    """One vector per passage (float32 bytes, 384-dim bge-small).

    Written at upload time; `model` versions the vector space so a future
    model swap never silently mixes spaces. Retrieval filters by module
    pool, ranks by cosine — passages stay unfiled under topics.
    """

    __tablename__ = "passage_embeddings"

    passage_id: Mapped[int] = mapped_column(
        ForeignKey("passages.id"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    vec: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    passage: Mapped[Passage] = relationship(back_populates="embedding")


class PassageNote(Base):
    """Tutor/learner annotations pinned to a passage — clarifications,
    cross-concept links, misconception warnings. Read back by get_passages
    context and the tutor so stored material gets better over time."""

    __tablename__ = "passage_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    passage_id: Mapped[int] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    passage: Mapped[Passage] = relationship(back_populates="notes")


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="mcq")  # mcq | short_answer | explain
    expected_key_points: Mapped[list] = mapped_column(JSON, default=list)
    images: Mapped[str | None] = mapped_column(String(512))  # filename(s)
    generated_by: Mapped[str | None] = mapped_column(String(64))  # model that made it

    topic: Mapped[Topic] = relationship(back_populates="questions")
    passage_links: Mapped[list[QuestionPassage]] = relationship(
        back_populates="question"
    )


class QuestionPassage(Base):
    __tablename__ = "question_passages"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id"), primary_key=True
    )
    passage_id: Mapped[int] = mapped_column(
        ForeignKey("passages.id"), primary_key=True
    )

    question: Mapped[Question] = relationship(back_populates="passage_links")
    passage: Mapped[Passage] = relationship(back_populates="question_links")


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="generating"
    )  # generating | ready | in_progress | completed | abandoned
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    questions: Mapped[list[AssessmentQuestion]] = relationship(
        back_populates="assessment"
    )


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (UniqueConstraint("assessment_id", "order_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    assessment: Mapped[Assessment] = relationship(back_populates="questions")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    user_answer: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    feedback: Mapped[str | None] = mapped_column(Text)  # LLM evaluation
    matched_key_points: Mapped[list] = mapped_column(JSON, default=list)
    missed_key_points: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(16), default="answered"
    )  # answered | skipped
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)  # malformed flag
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Preference(Base):
    __tablename__ = "preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    session_length_minutes: Mapped[int] = mapped_column(Integer, default=45)
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=180)
    preferred_start: Mapped[time | None] = mapped_column(Time)
    preferred_end: Mapped[time | None] = mapped_column(Time)
    tutor_instructions: Mapped[str | None] = mapped_column(Text)  # injected into tutor system prompt
    tutor_style: Mapped[str] = mapped_column(String(16), default="balanced")  # socratic | balanced | direct | drill
    tutor_verbosity: Mapped[str] = mapped_column(String(16), default="balanced")  # concise | balanced | detailed
    default_quiz_count: Mapped[int] = mapped_column(Integer, default=3)  # questions per topic when the tutor omits count
    default_difficulty: Mapped[str] = mapped_column(String(16), default="medium")  # easy | medium | hard
    review_batch_size: Mapped[int] = mapped_column(Integer, default=8)  # max recall cards per ask_review session
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="preference")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="Semester 3")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    slots: Mapped[list[Slot]] = relationship(back_populates="schedule")


class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("schedules.id"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-6
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="free")  # free | class | busy
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    schedule: Mapped[Schedule] = relationship(back_populates="slots")


class Deadline(Base):
    __tablename__ = "deadlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0-1.0
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    course: Mapped[Course] = relationship(back_populates="deadlines")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    last_source: Mapped[str | None] = mapped_column(String(32))  # what last moved the schedule
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    topic: Mapped[Topic] = relationship(back_populates="reviews")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    suggested_duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending | done | skipped | superseded
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class StudyLog(Base):
    """The missing entity: records actual study events, closing the loop
    between Plan generation and Proficiency update from real studying,
    not just quiz attempts."""

    __tablename__ = "study_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resources.id"))
    passage_id: Mapped[int | None] = mapped_column(ForeignKey("passages.id"))
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))
    minutes_spent: Mapped[int] = mapped_column(Integer, default=0)
    confidence_after: Mapped[float | None] = mapped_column(Float)  # 0.0-1.0
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class ProficiencyEvent(Base):
    """Ledger: every proficiency write, who/why, old → new. The answer to
    'why is my score X?' Sources: quiz_attempt | chat_understanding |
    study_log | manual_override. Retrieval scheduling (SM-2) reads recall
    events, never this table — mastery and retrieval stay separate."""

    __tablename__ = "proficiency_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    old_score: Mapped[float] = mapped_column(Float, default=0.0)
    new_score: Mapped[float] = mapped_column(Float, default=0.0)
    observed: Mapped[float] = mapped_column(Float, default=0.0)  # evidence value
    alpha: Mapped[float] = mapped_column(Float, default=0.0)  # blend weight used
    ref_id: Mapped[int | None] = mapped_column(Integer)  # attempt/log id, if any
    evidence: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Conversation(Base, TimestampMixin):
    """A tutor chat thread."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="Tutor chat")
    # Opaque, permanent ID for the external LLM provider. It must never be
    # derived from SQLite's reusable integer primary key.
    provider_thread_id: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=lambda: uuid4().hex
    )
    # Permanent module pin (None = unpinned free-form chat). Set at creation
    # from ui_context, changed only via set_context on the learner's words —
    # the tutor can never move or drop it on its own.
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id"), nullable=True)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    cards: Mapped[list[Card]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="Card.conversation_id",
    )


class ChatMessage(Base):
    """One turn in a conversation. role: user | assistant | tool."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Original data URLs for user-attached images. Kept separately from the
    # text transcript so history can render the attachment without feeding
    # old images back to the model on every later turn.
    images: Mapped[list[str] | None] = mapped_column(JSON)
    tool_calls: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(
        back_populates="messages"
    )


class Card(Base):
    """Inline UI card: quiz | clarify | review | todo | video.

    One row per card, created right after its turn's assistant message
    (id order == display order). payload is validated against the card
    schema in app/agent/cards.py. Replaces the legacy role='quiz'|... hack
    of smuggling payloads through ChatMessage.tool_calls.
    """

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id"), nullable=True
    )  # assistant message this card follows (display anchor)
    conversation: Mapped[Conversation] = relationship(
        back_populates="cards", foreign_keys=[conversation_id]
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class TutorMemory(Base, TimestampMixin):
    """Durable learner notes the tutor writes to itself across conversations
    (e.g. 'struggles with subnetting', 'prefers worked examples')."""

    __tablename__ = "tutor_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
