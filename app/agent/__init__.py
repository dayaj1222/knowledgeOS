"""The agent package — the integrated, modular 'core' of the app.

Exposes:
- core_agent          — the Pydantic-AI agent (tools + typed outputs)
- parse_syllabus      — syllabus text -> structured modules/topics
- skills.registry     — extensible skill registry (empty for now)
"""

from .core import (
    aevaluate_answer,
    agenerate_questions,
    core_agent,
    evaluate_answer,
    generate_questions,
    parse_syllabus,
)
from .skills import Skill, SkillRegistry, registry

__all__ = [
    "core_agent",
    "parse_syllabus",
    "generate_questions",
    "evaluate_answer",
    "agenerate_questions",
    "aevaluate_answer",
    "registry",
    "Skill",
    "SkillRegistry",
]
