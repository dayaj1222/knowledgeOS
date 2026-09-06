# Knowledge Base — local-first study companion

A personal study app: organize courses into modules and topics, upload materials
(PDF/slides/notes) that get chunked into passages, chat with an AI tutor grounded
in your content, take quizzes with AI grading, and track proficiency and study plans —
all in a local SQLite database.

## Features

- **AI tutor chat** (`/tutor`) — streaming conversation with a tool-using tutor:
  reads passages, checks proficiency/weaknesses/due reviews, searches the web,
  renders Mermaid diagrams, saves memories and passage notes.
- **In-chat quizzes** — ask the tutor for a quiz and it renders inline as sliding
  cards. Answers grade silently in the background per card; on finish the tutor
  debriefs you from the hidden results (grades are never shown, only the tutor
  sees them). The standalone quiz flow (`/quiz`) still exists for full sessions.
- **Library** (`/library`) — courses → modules → topics, material uploads with
  background extraction, per-passage annotations.
- **Quiz + grading** — AI-graded short answers with matched/missed key points,
  proficiency updates, SM-2 rescheduling, weak-point sync.
- **Planner** (`/plan`) — study plans, deadlines, study logs, dashboard.
- **Settings** (`/settings`) — tutor preferences and custom instructions.

## Stack

- Backend: **FastAPI** + SQLAlchemy + SQLite (`app/`), served on `:8000`.
- Frontend: **React + Vite + TypeScript + Tailwind/shadcn** (`frontend/`), dev on `:5173`.
- AI: any **OpenAI-compatible chat-completions endpoint** (local proxy, Ollama,
  vLLM, or a hosted API) with function calling.

## Prerequisites

- Python 3.14 + [`uv`](https://docs.astral.sh/uv/)
- Node 18+
- An OpenAI-compatible LLM endpoint reachable from the backend.

## Quickstart

```bash
# 1. Point the app at your model (or export KB_LLM_BASE_URL / KB_LLM_MODEL)
cp config.toml myconfig.toml   # optional; edit [llm] base_url + model
export KB_CONFIG="$PWD/myconfig.toml"

# 2. Install + run everything (backend :8000, frontend :5173)
./run.sh
```

Or run the pieces separately:

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000   # creates + migrates knowledge_base.db
cd frontend && npm install && npm run dev
```

Frontend production build: `cd frontend && npm run build` (must pass `tsc` clean).

### LLM configuration

Defaults live in `config.toml` (`[llm] base_url`, `model`) and can be overridden
per key with env vars: `KB_LLM_BASE_URL`, `KB_LLM_MODEL` (any `KB_<SECTION>_<KEY>`
works, or point `KB_CONFIG` at your own file). The tutor needs function-calling
support; grading and question generation fall back to keyword heuristics when the
endpoint is unreachable.

## Project layout

```
app/
  main.py            FastAPI app + router wiring (init_db on startup)
  models.py          All SQLAlchemy tables
  schemas.py         Pydantic request/response models
  database.py        Engine, sessions, migrations, default-user seed
  config.py          config.toml + KB_* env overrides
  ai.py              LLM client (question gen, answer eval, embeddings)
  protocol.py        ok()/fail() response envelope
  routers/           courses, topics, resources, questions, schedule, chat
  services/          quiz, review (SM-2), schedule, study logic
  agent/             Tutor agent: tool loop (tutor.py), 25 tools
                     (tutor_tools.py), prompts, web search/fetch (web.py)
  ingest/            Upload → text extraction → chunking pipeline
frontend/src/
  api.ts             Typed fetch client for the whole /api surface
  screens/           Tutor, Library, Dashboard, Plan, Settings
  pages/quiz/        QuizSetup, QuizTake, QuizResults (standalone flow)
  components/        Chat thread/composer, InlineQuiz, Markdown+Mermaid, …
storage/             Your uploads + local DB (gitignored, never committed)
```

## API surface

All endpoints live under `/api` (see `CONTEXT.md` for the full contract):

| Area | Examples |
|---|---|
| Chat | `POST /chat`, `POST /chat/stream` (SSE), `POST /chat/quiz/submit`, conversations, memories |
| Library | courses, modules, topics, resources + passages, passage notes |
| Quiz | questions, assessments, attempts + grading, weaknesses, drills |
| Planning | proficiency, study plans/logs, deadlines, preferences |

## Data & privacy

Single-user app (`USER_ID = 1` throughout). Everything — materials, database,
chat history — stays on your machine in `knowledge_base.db` and `storage/`,
both gitignored. Nothing is uploaded anywhere except the prompts your backend
sends to the LLM endpoint you configured.
