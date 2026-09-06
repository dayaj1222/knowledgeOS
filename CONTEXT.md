# Knowledge-Base — Agent Context & Coordination Doc

Read this whole file first. Then read the files listed in your assigned features. This is the single source of truth for how features map to code and how agents coordinate.

## Project root
The repository root (all paths below are relative to it).

## Files you must read (all paths relative to root)
- `app/models.py` — ALL tables. Read this fully before writing anything. You build against these exact tables/columns.
- `app/schemas.py` — Pydantic request/response models. Extend, don't rewrite.
- `app/database.py` — engine, `get_db`, `init_db`. Do not edit.
- `app/routers/*.py` — `courses.py`, `topics.py`, `resources.py`, `questions.py`, `schedule.py`. Endpoints already exist for most CRUD.
- `app/ai.py` — LLM stubs (`generate_questions`, `evaluate_answer`, `embed_text`, `is_available`). Return sentinels until wired. Do not call real LLM.
- `PLAN.md` — the full feature architecture (9 features, each with interaction→processing→storage→endpoints→frontend).
- `frontend/` — React + Vite + TS. `src/api.ts` (typed fetch client), `src/screens/*.tsx` (5 screens), `src/App.tsx` (routes). Catppuccin Mocha, Lucide icons, NO emoji, hardcoded `USER_ID=1`.

## The 9 features (from PLAN.md)
- F0: Course/Module/Topic full CRUD (spine)
- F1: Material upload → passage extraction
- F2: Proficiency display + override
- F3: Quiz (take, grade, update proficiency)
- F4: Question generation (AI, stubbed)
- F5: Scheduler (study plan)
- F6: Study logging (closes loop)
- F7: Settings real form
- F8: Deadlines + weight

## Coordination rules (READ CAREFULLY)

**Three agents, three ownership domains. Do NOT edit files outside your domain.**

- **Agent A — BACKEND DATA + EXTRACTION** owns `app/routers/resources.py`, `app/ai.py` (add stub calls only), and a NEW `app/extract.py`. Features: F1 (upload→passages), F4 (question gen stub wiring in `questions.py`).
- **Agent B — BACKEND LOGIC + SCHEDULER** owns `app/routers/schedule.py`, `app/routers/questions.py`, `app/schemas.py`, and a NEW `app/scheduler.py`. Features: F2 (proficiency), F3 (quiz), F5 (scheduler), F6 (study logs), F8 (deadlines).
- **Agent C — FRONTEND** owns everything under `frontend/`. Features: F0 (CRUD UI), F2 (proficiency display), F3 (quiz UI), F7 (settings form), F8 (deadline form). Reads the endpoint contracts the backend agents write.

**Shared files — only ONE agent edits each:**
- `app/schemas.py` → Agent B owns it. Agents A and C READ it only.
- `app/routers/topics.py` → has Preference + Proficiency endpoints already (F2/F7 are mostly done). Agent B owns; A and C read.
- `app/ai.py` → Agent A owns (it's the LLM-stub home). B reads.
- `app/routers/questions.py` → Agent B owns (quiz). A only adds the generate-questions stub call, and MUST NOT conflict with B's quiz edits — coordinate via the shared endpoint list below.

**Endpoint contract (the coordination surface).** Every agent MUST use these exact paths/methods, so the frontend (Agent C) wires correctly without guessing:

| Purpose | Method + Path | Body | Owner |
|---|---|---|---|
| Upload material | `POST /api/courses/{id}/resources` | multipart (file, name, type) | A |
| List passages | `GET /api/resources/{id}/passages` | — | A (exists) |
| Generate questions | `POST /api/topics/{id}/generate-questions` | `{count, type}` | A (stub wiring) |
| List questions | `GET /api/topics/{id}/questions` | — | B (exists) |
| Create assessment | `POST /api/assessments` | `{user_id}` (NO /users prefix) | B |
| Create attempt | `POST /api/attempts` | `{user_id, assessment_id, question_id, user_answer}` | B |
| Grade attempt | `PATCH /api/attempts/{id}/grade` | `{score, feedback?, status?, excluded?}` | B |
| List proficiency | `GET /api/users/{id}/proficiency` | — | B (exists) |
| Upsert proficiency | `PUT /api/users/{id}/proficiency/{topic_id}` | `{score?, weak_points?, strengths?, preferred_method?}` | B |
| Generate plan | `POST /api/users/{id}/generate-plan` | `{}` | B |
| List plans | `GET /api/users/{id}/plans` | — | B (exists) |
| Mark plan done | `PATCH /api/plans/{id}` | `{status}` | B |
| Study log | `POST /api/study-logs` | `{topic_id, minutes_spent, confidence_after?, resource_id?}` | B |
| Tutor chat | `POST /api/chat` → `{conversation_id?, reply, tool_calls, ui_actions}` (+ conversation history endpoints) | `{message, conversation_id?}` | Tutor agent (`app/agent/tutor.py` + `tutor_tools.py`) |
| List study logs | `GET /api/users/{id}/study-logs` | — | B |
| Deadlines | `POST /api/deadlines` + `GET /api/users/{id}/deadlines` | `{user_id, course_id, title, due_date, weight?, topic_id?}` | B (exists) |
| Preference | `GET`+`PUT /api/users/{id}/preference` | `{session_length_minutes?, daily_goal_minutes?, preferred_start?, preferred_end?}` | B (exists) |
| Courses CRUD | `POST/GET /api/users/{id}/courses` | see schema | exists |
| Modules | `POST/GET /api/courses/{id}/modules` | see schema | exists |
| Topics | `POST /api/topics` + `GET /api/modules/{id}/topics` | see schema | exists |

**Do NOT invent new endpoints** — if the contract above has it, use it. If you need something not listed, STOP and note it in your report rather than silently adding a conflicting route.

## Verification rules
- Every feature: run the actual endpoint (curl or in-process) and report the REAL output. Do not fabricate passing results.
- Frontend (Agent C): `npm run build` must pass with zero TS errors, AND `api.ts` must use the exact contract paths above.

## Definitions of done
Each agent reports: which files it changed, the exact curl/build output proving each feature works, and any endpoint it needed but found missing.
