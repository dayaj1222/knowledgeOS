"""Business service layer for Knowledge Base.

Contains reusable, modular, and testable service logic separated from HTTP routers:
- course_service: course hierarchy, counts, and tree navigation
- schedule_service: deadline management, study-need scoring, and automated study plan generation
- quiz_service: questions, multi-topic quiz synthesis, rubric evaluation, attempt scoring,
  weakness diagnosis, and targeted drill generation
- study_service: study session logging, progress tracking, and proficiency updates
- review_service: SM-2 spaced repetition scheduling and due queues
"""

from .course_service import CourseService
from .proficiency_service import (
    CHAT_UNDERSTANDING,
    MANUAL_OVERRIDE,
    QUIZ_ATTEMPT,
    STUDY_LOG,
    ProficiencyService,
)
from .quiz_service import QuizService
from .review_service import ReviewService, score_to_quality, sm2_step
from .schedule_service import ScheduleService
from .study_service import StudyService

__all__ = [
    "CourseService",
    "ScheduleService",
    "QuizService",
    "StudyService",
    "ReviewService",
    "ProficiencyService",
    "QUIZ_ATTEMPT",
    "CHAT_UNDERSTANDING",
    "STUDY_LOG",
    "MANUAL_OVERRIDE",
    "sm2_step",
    "score_to_quality",
]
