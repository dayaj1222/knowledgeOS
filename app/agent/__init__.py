"""The agent package — the integrated, modular 'core' of the app.

Exposes:
- core_agent          — the Pydantic-AI agent (tools + typed outputs)
- parse_syllabus      — syllabus text -> structured modules/topics
- tag_passages        — passages -> topic assignments
- skills.registry     — extensible skill registry (empty for now)
"""

from .core import (
    core_agent,
    parse_syllabus,
    tag_passages_to_topics,
    generate_questions,
    evaluate_answer,
    agenerate_questions,
    aevaluate_answer,
)
from .skills import registry, Skill, SkillRegistry

__all__ = [
    "core_agent",
    "parse_syllabus",
    "tag_passages_to_topics",
    "generate_questions",
    "evaluate_answer",
    "agenerate_questions",
    "aevaluate_answer",
    "registry",
    "Skill",
    "SkillRegistry",
]
