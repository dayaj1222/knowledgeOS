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
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
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
    college: Mapped[Optional[str]] = mapped_column(String(255))
    course_name: Mapped[str] = mapped_column(String(255), default="B.Tech CSE")
    semester: Mapped[Optional[int]] = mapped_column(Integer)
    location: Mapped[Optional[str]] = mapped_column(String(255))

    courses: Mapped[list["Course"]] = relationship(back_populates="user")
    proficiency: Mapped[list["Proficiency"]] = relationship(back_populates="user")
    preference: Mapped[Optional["Preference"]] = relationship(back_populates="user", uselist=False)


class Course(Base, TimestampMixin):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="ETH")  # TH | ETH | ELA
    instructor: Mapped[Optional[str]] = mapped_column(String(255))
    credits: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(
        String(16), default="not_started"
    )  # not_started | in_progress | completed
    color: Mapped[Optional[str]] = mapped_column(String(16))

    user: Mapped["User"] = relationship(back_populates="courses")
    modules: Mapped[list["Module"]] = relationship(back_populates="course")
    resources: Mapped[list["Resource"]] = relationship(back_populates="course")
    deadlines: Mapped[list["Deadline"]] = relationship(back_populates="course")


class Module(Base, TimestampMixin):
    """A syllabus unit grouping topics. CATs/exams are scoped to modules."""

    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped["Course"] = relationship(back_populates="modules")
    topics: Mapped[list["Topic"]] = relationship(back_populates="module")


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), nullable=False)
    parent_topic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("topics.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)  # query side for matching
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1-5 exam importance
    prerequisite_ids: Mapped[list] = mapped_column(JSON, default=list)

    module: Mapped["Module"] = relationship(back_populates="topics")
    children: Mapped[list["Topic"]] = relationship(
        back_populates="parent", remote_side=[id]
    )
    parent: Mapped[Optional["Topic"]] = relationship(
        back_populates="children", remote_side=[parent_topic_id]
    )
    questions: Mapped[list["Question"]] = relationship(back_populates="topic")
    proficiency: Mapped[list["Proficiency"]] = relationship(back_populates="topic")
    reviews: Mapped[list["Review"]] = relationship(back_populates="topic")


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

    user: Mapped["User"] = relationship(back_populates="proficiency")
    topic: Mapped["Topic"] = relationship(back_populates="proficiency")


class Resource(Base, TimestampMixin):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="pdf")  # pdf | slides | notes
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    module_id: Mapped[Optional[int]] = mapped_column(ForeignKey("modules.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="uploaded"
    )  # uploaded | processing | done | partial | failed
    error: Mapped[Optional[str]] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    course: Mapped["Course"] = relationship(back_populates="resources")
    passages: Mapped[list["Passage"]] = relationship(back_populates="resource")


class Passage(Base):
    __tablename__ = "passages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    index_order: Mapped[int] = mapped_column(Integer, default=0)
    topic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topics.id"), nullable=True)
    page_start: Mapped[Optional[int]] = mapped_column(Integer)
    page_end: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    resource: Mapped["Resource"] = relationship(back_populates="passages")
    question_links: Mapped[list["QuestionPassage"]] = relationship(
        back_populates="passage"
    )
    notes: Mapped[list["PassageNote"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan"
    )


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

    passage: Mapped["Passage"] = relationship(back_populates="notes")


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="mcq")  # mcq | short_answer | explain
    expected_key_points: Mapped[list] = mapped_column(JSON, default=list)
    images: Mapped[Optional[str]] = mapped_column(String(512))  # filename(s)
    generated_by: Mapped[Optional[str]] = mapped_column(String(64))  # model that made it

    topic: Mapped["Topic"] = relationship(back_populates="questions")
    passage_links: Mapped[list["QuestionPassage"]] = relationship(
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

    question: Mapped["Question"] = relationship(back_populates="passage_links")
    passage: Mapped["Passage"] = relationship(back_populates="question_links")


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
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    questions: Mapped[list["AssessmentQuestion"]] = relationship(
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

    assessment: Mapped["Assessment"] = relationship(back_populates="questions")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), nullable=False)
    user_answer: Mapped[Optional[str]] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    feedback: Mapped[Optional[str]] = mapped_column(Text)  # LLM evaluation
    matched_key_points: Mapped[list] = mapped_column(JSON, default=list)
    missed_key_points: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(16), default="answered"
    )  # answered | skipped
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)  # malformed flag
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Preference(Base):
    __tablename__ = "preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    session_length_minutes: Mapped[int] = mapped_column(Integer, default=45)
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=180)
    preferred_start: Mapped[Optional[time]] = mapped_column(Time)
    preferred_end: Mapped[Optional[time]] = mapped_column(Time)
    tutor_instructions: Mapped[Optional[str]] = mapped_column(Text)  # injected into tutor system prompt
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="preference")


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

    slots: Mapped[list["Slot"]] = relationship(back_populates="schedule")


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

    schedule: Mapped["Schedule"] = relationship(back_populates="slots")


class Deadline(Base):
    __tablename__ = "deadlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    topic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("topics.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0-1.0
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    course: Mapped["Course"] = relationship(back_populates="deadlines")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    topic: Mapped["Topic"] = relationship(back_populates="reviews")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("slots.id"))
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
    resource_id: Mapped[Optional[int]] = mapped_column(ForeignKey("resources.id"))
    passage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("passages.id"))
    plan_id: Mapped[Optional[int]] = mapped_column(ForeignKey("plans.id"))
    minutes_spent: Mapped[int] = mapped_column(Integer, default=0)
    confidence_after: Mapped[Optional[float]] = mapped_column(Float)  # 0.0-1.0
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Conversation(Base, TimestampMixin):
    """A tutor chat thread."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="Tutor chat")

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
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
    tool_calls: Mapped[Optional[list]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )


class TutorMemory(Base, TimestampMixin):
    """Durable learner notes the tutor writes to itself across conversations
    (e.g. 'struggles with subnetting', 'prefers worked examples')."""

    __tablename__ = "tutor_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
