"""The core agent — a Pydantic-AI agent bound to an OpenAI-compatible endpoint.

Structured-output tasks (syllabus → modules/topics, passage → topic) use
Pydantic-AI's `output_type` mechanism, which is implemented AS an OpenAI
tool-call under the hood: the framework declares a tool schema from the
Pydantic return type and parses the model's tool-call arguments. We do NOT
re-specify "return JSON in this shape" in the prompt.

Prompt model: BASE_PROMPT (always on) is assembled with a per-task fragment
before each call (app.agent.prompt.assemble). Procedural tools (web search,
commands) register via @core_agent.tool later.

Passage tagging is BATCHED: passages are split into groups of
settings.agent.tag_batch_size and the LLM is called once per batch (all topics
each time), then results are merged. This keeps each call's structured return
small enough to be reliable — one giant call invites skipped/hallucinated rows.

Embeddings stay local (sentence-transformers), separate from this agent.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ..config import settings
from .models import (
    AnswerEvaluation,
    GeneratedQuestions,
    SyllabusStructure,
)
from .prompt import assemble

_model = OpenAIChatModel(
    model_name=settings.llm.model,
    provider=OpenAIProvider(base_url=settings.llm.base_url, api_key="local"),
)

core_agent = Agent(
    model=_model,
    system_prompt=assemble("base"),
    deps_type=dict,
)


# --- Typed tasks (structured output via output_type = OpenAI tool-call) ---

def parse_syllabus(syllabus_text: str) -> SyllabusStructure:
    """Syllabus text → structured modules + topics (self-repairing schema)."""
    result = core_agent.run_sync(
        f"Extract the module/topic structure from this syllabus:\n\n{syllabus_text[:12000]}",
        deps={},
        instructions=assemble("parse_syllabus"),
        output_type=SyllabusStructure,
    )
    return result.output


# --- Question generation + answer evaluation (typed, self-repairing) ---

def generate_questions(
    topic_name: str,
    passages: list[str],
    count: int,
    difficulty: str = "medium",
    instructions: str = "",
) -> GeneratedQuestions:
    """Generate `count` questions grounded in a topic's passage text."""
    context = "\n\n".join(p[:1200] for p in passages[:6]) or "(no passage text)"
    difficulty_hint = {
        "easy": "recall and basic definitions",
        "medium": "understanding and application",
        "hard": "analysis, synthesis, edge cases, and 'why/how' reasoning",
    }.get(difficulty, "understanding and application")
    custom = f"\nCUSTOM INSTRUCTIONS: {instructions}" if instructions.strip() else ""
    result = core_agent.run_sync(
        (
            f"Generate {count} short-answer questions at difficulty '{difficulty}' "
            f"({difficulty_hint}) that test understanding of the topic '{topic_name}'. "
            "Ground each question in the material below. "
            "For each question, list the key points a correct answer must cover. "
            "Prefer 'why' and 'how' questions over pure definitions."
            f"{custom}\n\nMATERIAL:\n{context}"
        ),
        deps={},
        instructions=assemble("generate_questions"),
        output_type=GeneratedQuestions,
    )
    return result.output


async def agenerate_questions(
    topic_name: str,
    passages: list[str],
    count: int,
    difficulty: str = "medium",
    instructions: str = "",
) -> GeneratedQuestions:
    """Async twin of generate_questions — safe inside a running event loop
    (the tutor's streaming path). Sync callers keep using generate_questions.
    """
    context = "\n\n".join(p[:1200] for p in passages[:6]) or "(no passage text)"
    difficulty_hint = {
        "easy": "recall and basic definitions",
        "medium": "understanding and application",
        "hard": "analysis, synthesis, edge cases, and 'why/how' reasoning",
    }.get(difficulty, "understanding and application")
    custom = f"\nCUSTOM INSTRUCTIONS: {instructions}" if instructions.strip() else ""
    result = await core_agent.run(
        (
            f"Generate {count} short-answer questions at difficulty '{difficulty}' "
            f"({difficulty_hint}) that test understanding of the topic '{topic_name}'. "
            "Ground each question in the material below. "
            "For each question, list the key points a correct answer must cover. "
            "Prefer 'why' and 'how' questions over pure definitions."
            f"{custom}\n\nMATERIAL:\n{context}"
        ),
        deps={},
        instructions=assemble("generate_questions"),
        output_type=GeneratedQuestions,
    )
    return result.output


def evaluate_answer(
    question_text: str,
    expected_key_points: list[str],
    user_answer: str,
    passages: list[str] | None = None,
    weaknesses: list | None = None,
) -> AnswerEvaluation:
    """Grade an answer (LLM) against expected key points + context."""
    passage_ctx = "\n\n".join(p[:1000] for p in (passages or [])[:3])
    weakness_ctx = ", ".join(str(w) for w in (weaknesses or [])) if weaknesses else "(none known)"
    result = core_agent.run_sync(
        (
            "Grade this answer against the expected key points. "
            "Score 0.0-1.0 by how fully it covers them. List which key points "
            "were matched and which were missed. Be fair to correct paraphrases.\n\n"
            f"QUESTION: {question_text}\n"
            f"EXPECTED KEY POINTS: {', '.join(expected_key_points) if expected_key_points else '(none)'}\n"
            f"STUDENT'S KNOWN WEAKNESSES (context): {weakness_ctx}\n"
            f"GROUNDING MATERIAL:\n{passage_ctx or '(none)'}\n\n"
            f"STUDENT ANSWER: {user_answer or '(empty)'}"
        ),
        deps={},
        instructions=assemble("evaluate_answer"),
        output_type=AnswerEvaluation,
    )
    return result.output


async def aevaluate_answer(
    question_text: str,
    expected_key_points: list[str],
    user_answer: str,
    passages: list[str] | None = None,
    weaknesses: list | None = None,
) -> AnswerEvaluation:
    """Async twin of evaluate_answer — safe inside a running event loop."""
    passage_ctx = "\n\n".join(p[:1000] for p in (passages or [])[:3])
    weakness_ctx = ", ".join(str(w) for w in (weaknesses or [])) if weaknesses else "(none known)"
    result = await core_agent.run(
        (
            "Grade this answer against the expected key points. "
            "Score 0.0-1.0 by how fully it covers them. List which key points "
            "were matched and which were missed. Be fair to correct paraphrases.\n\n"
            f"QUESTION: {question_text}\n"
            f"EXPECTED KEY POINTS: {', '.join(expected_key_points) if expected_key_points else '(none)'}\n"
            f"STUDENT'S KNOWN WEAKNESSES (context): {weakness_ctx}\n"
            f"GROUNDING MATERIAL:\n{passage_ctx or '(none)'}\n\n"
            f"STUDENT ANSWER: {user_answer or '(empty)'}"
        ),
        deps={},
        instructions=assemble("evaluate_answer"),
        output_type=AnswerEvaluation,
    )
    return result.output
