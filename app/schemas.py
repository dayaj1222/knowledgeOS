"""Pydantic schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---- Base config ----
class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- User ----
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    timezone: str = "Asia/Kolkata"
    college: Optional[str] = None
    course_name: str = "B.Tech CSE"
    semester: Optional[int] = None
    location: Optional[str] = None


class UserOut(ORMModel):
    id: int
    name: str
    email: EmailStr
    timezone: str
    college: Optional[str] = None
    course_name: str
    semester: Optional[int] = None
    location: Optional[str] = None


# ---- Course ----
class CourseCreate(BaseModel):
    name: str
    code: str
    type: str = "ETH"
    instructor: Optional[str] = None
    credits: int = 3
    color: Optional[str] = None


class CourseUpdate(BaseModel):
    status: Optional[str] = None
    color: Optional[str] = None
    instructor: Optional[str] = None


class CourseOut(ORMModel):
    id: int
    user_id: int
    name: str
    code: str
    type: str
    instructor: Optional[str] = None
    credits: int
    status: str
    color: Optional[str] = None


# ---- Module ----
class ModuleCreate(BaseModel):
    name: str
    order_index: int = 0


class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    order_index: Optional[int] = None


class ModuleOut(ORMModel):
    id: int
    course_id: int
    name: str
    order_index: int


# ---- Topic ----
class TopicCreate(BaseModel):
    module_id: int
    name: str
    description: Optional[str] = None
    parent_topic_id: Optional[int] = None
    order_index: int = 0
    priority: int = Field(default=3, ge=1, le=5)
    prerequisite_ids: list[int] = []


class TopicOut(ORMModel):
    id: int
    module_id: int
    parent_topic_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    order_index: int
    priority: int
    prerequisite_ids: list[int]
    passage_count: int = 0


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_topic_id: Optional[int] = None
    order_index: Optional[int] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    prerequisite_ids: Optional[list[int]] = None


# ---- Proficiency ----
class ProficiencyUpdate(BaseModel):
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    weak_points: Optional[list] = None
    strengths: Optional[list] = None
    preferred_method: Optional[str] = None


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
    error: Optional[str] = None


class PassageCreate(BaseModel):
    resource_id: int
    content: str
    index_order: int = 0


class PassageOut(ORMModel):
    id: int
    resource_id: int
    content: str
    index_order: int
    topic_id: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


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
    images: Optional[str] = None


class QuestionOut(ORMModel):
    id: int
    topic_id: int
    text: str
    type: str
    expected_key_points: list
    images: Optional[str] = None
    generated_by: Optional[str] = None


# ---- Assessment ----
class AssessmentCreate(BaseModel):
    user_id: int


class AssessmentOut(ORMModel):
    id: int
    user_id: int
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


# ---- Attempt ----
class AttemptCreate(BaseModel):
    user_id: int
    assessment_id: int
    question_id: int
    user_answer: Optional[str] = None


class AttemptGrade(BaseModel):
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    feedback: Optional[str] = None
    # Optional revised answer: when the learner edits an already-created
    # attempt (e.g. in-chat quiz card), update user_answer in place and
    # re-grade the SAME attempt instead of creating duplicates.
    user_answer: Optional[str] = None
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
    user_answer: Optional[str] = None
    score: float
    feedback: Optional[str] = None
    matched_key_points: list[str] = []
    missed_key_points: list[str] = []
    status: str
    excluded: bool


# ---- Preference ----
class PreferenceUpdate(BaseModel):
    session_length_minutes: Optional[int] = None
    daily_goal_minutes: Optional[int] = None
    preferred_start: Optional[time] = None
    preferred_end: Optional[time] = None
    tutor_instructions: Optional[str] = None


class PreferenceOut(ORMModel):
    user_id: int
    session_length_minutes: int
    daily_goal_minutes: int
    preferred_start: Optional[time] = None
    preferred_end: Optional[time] = None
    tutor_instructions: Optional[str] = None


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
    topic_id: Optional[int] = None
    weight: float = Field(default=0.0, ge=0.0, le=1.0)


class DeadlineOut(ORMModel):
    id: int
    user_id: int
    course_id: int
    topic_id: Optional[int] = None
    title: str
    due_date: datetime
    weight: float


# ---- Plan ----
class PlanUpdate(BaseModel):
    status: str


class PlanOut(ORMModel):
    id: int
    user_id: int
    slot_id: Optional[int] = None
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
    confidence_after: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    resource_id: Optional[int] = None
    passage_id: Optional[int] = None
    plan_id: Optional[int] = None


class StudyLogOut(ORMModel):
    id: int
    user_id: int
    topic_id: int
    resource_id: Optional[int] = None
    passage_id: Optional[int] = None
    plan_id: Optional[int] = None
    minutes_spent: int
    confidence_after: Optional[float] = None


# ---- Spaced repetition ----
class ReviewResultCreate(BaseModel):
    user_id: int
    topic_id: int
    quality: int = Field(ge=0, le=5)  # SM-2 recall quality


# ---- Targeted drill ----
class DrillRequest(BaseModel):
    user_id: int
    topic_id: Optional[int] = None  # none = weakest topics by miss count
    count: int = Field(default=5, ge=1, le=25)
    difficulty: str = "medium"


# ---- Tutor chat ----
class ChatRequest(BaseModel):
    user_id: int = 1
    conversation_id: Optional[int] = None
    message: str = Field(min_length=1, max_length=8000)
    ui_context: Optional[dict] = None  # {route, course_id, course_name, ...}


class ChatMessageOut(ORMModel):
    id: int
    role: str
    content: str
    tool_calls: Optional[list] = None


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
