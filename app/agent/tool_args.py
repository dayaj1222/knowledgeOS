"""Runtime argument models for tutor tools.

Kept apart from implementations so schema validation and tool behaviour can
evolve independently.  The registry imports these models as its contract.
"""

from pydantic import BaseModel, Field


class RecordUnderstandingArgs(BaseModel):
    topic_id: int
    demonstrated: float = 0.8
    coverage: float = 0.2
    evidence: str = ""
    confirmed: bool = False


class UpdateTodoArgs(BaseModel):
    todos: list[dict]
    confirmed: bool = False


class GenerateQuizArgs(BaseModel):
    topic_ids: list[int] = Field(default_factory=list)
    count_per_topic: int | None = None
    difficulty: str | None = None
    confirmed: bool = False


class AskClarifyArgs(BaseModel):
    question: str = ""
    options: list[str] = Field(default_factory=list)
    allow_free_text: bool = True


class AskReviewArgs(BaseModel):
    items: list[dict]


class FindVideosArgs(BaseModel):
    query: str
    count: int | None = None
    topic_id: int | None = None


class StartTimerArgs(BaseModel):
    topic_id: int
    label: str = ""


class ShowDemoArgs(BaseModel):
    title: str = "Interactive demo"
    html: str
    height: int | None = None


class RunCodeArgs(BaseModel):
    code: str
    timeout: float | None = None


class PlotChartArgs(BaseModel):
    code: str
    title: str = "Figure"
    timeout: float | None = None
