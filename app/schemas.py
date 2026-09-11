"""Pydantic schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---- Base config ----
class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- User ----
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    timezone: str = "Asia/Kolkata"
    college: str | None = None
    course_name: str = "B.Tech CSE"
    semester: int | None = None
    location: str | None = None


class UserOut(ORMModel):
    id: int
    name: str
    email: EmailStr
    timezone: str
    college: str | None = None
    course_name: str
    semester: int | None = None
    location: str | None = None


# ---- Course ----
class CourseCreate(BaseModel):
    name: str
    code: str
    type: str = "ETH"
    instructor: str | None = None
    credits: int = 3
    color: str | None = None


class CourseUpdate(BaseModel):
    status: str | None = None
    color: str | None = None
    instructor: str | None = None


class CourseOut(ORMModel):
    id: int
    user_id: int
    name: str
    code: str
    type: str
    instructor: str | None = None
    credits: int
    status: str
    color: str | None = None


# ---- Module ----
class ModuleCreate(BaseModel):
    name: str
    order_index: int = 0


class ModuleUpdate(BaseModel):
    name: str | None = None
    order_index: int | None = None


class ModuleOut(ORMModel):
    id: int
    course_id: int
    name: str
    order_index: int


# ---- Topic ----
class TopicCreate(BaseModel):
    module_id: int
    name: str
    description: str | None = None
    parent_topic_id: int | None = None
    order_index: int = 0
    priority: int = Field(default=3, ge=1, le=5)
    prerequisite_ids: list[int] = []


class TopicOut(ORMModel):
    id: int
    module_id: int
    parent_topic_id: int | None = None
    name: str
    description: str | None = None
    order_index: int
    priority: int
    prerequisite_ids: list[int]
    passage_count: int = 0


class TopicUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parent_topic_id: int | None = None
    order_index: int | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    prerequisite_ids: list[int] | None = None


# ---- Proficiency ----
class ProficiencyUpdate(BaseModel):
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    weak_points: list | None = None
    strengths: list | None = None
    preferred_method: str | None = None


class ProficiencyOut(ORMModel):
    user_id: int
    topic_id: int
    score: float
    weak_points: list
    strengths: list
    preferred_method: str
    last_updated: datetime


# ---- Resource / Passage ----
class ResourceCreate(BaseModel):
    name: str
    course_id: int
    type: str = "pdf"
    file_path: str


class ResourceOut(ORMModel):
    id: int
    user_id: int
    course_id: int
    name: str
    type: str
    file_path: str
    status: str = "uploaded"
    error: str | None = None


class PassageCreate(BaseModel):
    resource_id: int
    content: str
    index_order: int = 0


class PassageOut(ORMModel):
    id: int
    resource_id: int
    content: str
    index_order: int
    topic_id: int | None = None
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class PassageNoteCreate(BaseModel):
    user_id: int = 1
    note: str


class PassageNoteOut(ORMModel):
    id: int
    passage_id: int
    user_id: int
    note: str
    created_at: datetime


# ---- Question ----
class QuestionCreate(BaseModel):
    topic_id: int
    text: str
    type: str = "mcq"
    expected_key_points: list = []
    images: str | None = None


class QuestionOut(ORMModel):
    id: int
    topic_id: int
    text: str
    type: str
    expected_key_points: list
    images: str | None = None
    generated_by: str | None = None


# ---- Assessment ----
class AssessmentCreate(BaseModel):
    user_id: int


class AssessmentOut(ORMModel):
    id: int
    user_id: int
    status: str
    created_at: datetime
    completed_at: datetime | None = None


# ---- Attempt ----
class AttemptCreate(BaseModel):
    user_id: int
    assessment_id: int
    question_id: int
    user_answer: str | None = None


class AttemptGrade(BaseModel):
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    feedback: str | None = None
    # Optional revised answer: when the learner edits an already-created
    # attempt (e.g. in-chat quiz card), update user_answer in place and
    # re-grade the SAME attempt instead of creating duplicates.
    user_answer: str | None = None
    status: str = "answered"
    excluded: bool = False


class ChatQuizSubmit(BaseModel):
    """Finish an in-chat quiz: stock-take already-graded attempts, run the
    hidden tutor debrief, and return ONLY the tutor's recommendation."""
    user_id: int = 1
    conversation_id: int
    assessment_id: int


class AttemptOut(ORMModel):
    id: int
    user_id: int
    assessment_id: int
    question_id: int
    user_answer: str | None = None
    score: float
    feedback: str | None = None
    matched_key_points: list[str] = []
    missed_key_points: list[str] = []
    status: str
    excluded: bool


# ---- Preference ----
class PreferenceUpdate(BaseModel):
    session_length_minutes: int | None = None
    daily_goal_minutes: int | None = None
    preferred_start: time | None = None
    preferred_end: time | None = None
    tutor_instructions: str | None = None
    tutor_style: str | None = None
    tutor_verbosity: str | None = None
    default_quiz_count: int | None = None
    default_difficulty: str | None = None
    review_batch_size: int | None = None


class PreferenceOut(ORMModel):
    user_id: int
    session_length_minutes: int
    daily_goal_minutes: int
    preferred_start: time | None = None
    preferred_end: time | None = None
    tutor_instructions: str | None = None
    tutor_style: str = "balanced"
    tutor_verbosity: str = "balanced"
    default_quiz_count: int = 3
    default_difficulty: str = "medium"
    review_batch_size: int = 8


# ---- Schedule / Slot ----
class ScheduleCreate(BaseModel):
    user_id: int
    name: str = "Semester 3"


class ScheduleOut(ORMModel):
    id: int
    user_id: int
    name: str


class SlotCreate(BaseModel):
    schedule_id: int
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    type: str = "free"


class SlotOut(ORMModel):
    id: int
    schedule_id: int
    day_of_week: int
    start_time: time
    end_time: time
    type: str


# ---- Deadline ----
class DeadlineCreate(BaseModel):
    user_id: int
    course_id: int
    title: str
    due_date: datetime
    topic_id: int | None = None
    weight: float = Field(default=0.0, ge=0.0, le=1.0)


class DeadlineOut(ORMModel):
    id: int
    user_id: int
    course_id: int
    topic_id: int | None = None
    title: str
    due_date: datetime
    weight: float


# ---- Plan ----
class PlanUpdate(BaseModel):
    status: str


class PlanOut(ORMModel):
    id: int
    user_id: int
    slot_id: int | None = None
    topic_id: int
    suggested_duration_minutes: int
    status: str
    generated_at: datetime


# ---- AI stub ----
class GenerateRequest(BaseModel):
    topic_id: int
    count: int = 3
    type: str = "mcq"


class QuizGenerateRequest(BaseModel):
    topic_ids: list[int]
    questions_per_topic: int = 3
    difficulty: str = "medium"  # easy | medium | hard
    instructions: str = ""


class EmbedRequest(BaseModel):
    passage_id: int


# ---- Study log ----
class StudyLogCreate(BaseModel):
    user_id: int
    topic_id: int
    minutes_spent: int = Field(ge=0)
    confidence_after: float | None = Field(default=None, ge=0.0, le=1.0)
    resource_id: int | None = None
    passage_id: int | None = None
    plan_id: int | None = None


class StudyLogOut(ORMModel):
    id: int
    user_id: int
    topic_id: int
    resource_id: int | None = None
    passage_id: int | None = None
    plan_id: int | None = None
    minutes_spent: int
    confidence_after: float | None = None
    created_at: datetime | None = None


# ---- Spaced repetition ----
class ReviewResultCreate(BaseModel):
    user_id: int
    topic_id: int
    quality: int = Field(ge=0, le=5)  # SM-2 recall quality


# ---- Targeted drill ----
class DrillRequest(BaseModel):
    user_id: int
    topic_id: int | None = None  # none = weakest topics by miss count
    count: int = Field(default=5, ge=1, le=25)
    difficulty: str = "medium"


# ---- Tutor chat ----
class ChatRequest(BaseModel):
    user_id: int = 1
    conversation_id: int | None = None
    message: str = Field(min_length=1, max_length=8000)
    ui_context: dict | None = None  # {route, course_id, course_name, ...}


class ChatMessageOut(ORMModel):
    id: int
    role: str
    content: str
    tool_calls: list | None = None


class ConversationOut(ORMModel):
    id: int
    title: str


class ChatResponse(BaseModel):
    conversation_id: int
    reply: str
    tool_calls: list = []
    ui_actions: list = []


class TutorMemoryUpsert(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2000)
