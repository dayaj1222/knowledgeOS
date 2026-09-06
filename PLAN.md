# Knowledge-Base — Feature Architecture Plan

Each feature planned front-to-back: user interaction → processing → storage → how it maps to the existing schema. Built against the CURRENT models (`app/models.py`) and routers. Order = build order (each depends on the previous).

---

## Feature 0: Course / Module / Topic — full CRUD (the spine)

**What the user does:** On the dashboard, creates a Course (name, code, type TH/ETH/ELA). Opens it, creates Modules ("Module 1: Network Models"). Opens a module, creates Topics ("OSI Model", "TCP/IP"), each with optional description + priority (1–5) + prerequisites.

**Processing:** None — pure CRUD. The topic `description` keeps the topic's scope explicit for the LLM tagger and question generation, so it should be editable and kept meaningful. Prerequisites are stored as a JSON list of topic IDs; the UI shows them as a multi-select of sibling topics.

**Storage:** `courses`, `modules`, `topics` tables (already exist). Relationships: Course → Modules → Topics, and Topic.parent_topic_id for subtopics.

**Endpoints (all exist):**
- `POST /api/users/{id}/courses`, `GET /api/users/{id}/courses`
- `POST /api/courses/{id}/modules`, `GET /api/courses/{id}/modules`
- `POST /api/topics`, `GET /api/modules/{id}/topics`

**Frontend:** Dashboard lists courses (click → Course screen). Course screen lists modules (expandable → topics). Topic form: name, description, priority (1–5 stepper), prerequisites (checkbox list of peers). **This is the missing spine — today's UI has a stub list, not a walkable tree.**

**Fit:** Everything else attaches to Topic. No topic = nothing to study, quiz, or plan.

---

## Feature 1: Material Upload → Passage Extraction

**What the user does:** On a Course screen, an "Upload material" button. Drops a PDF/slides file, picks type (pdf/slides/notes), names it. Sees it appear in the course's resource list with a "passage count" that grows as extraction happens.

**Processing (two phases):**
1. **Store the file** — save to `storage/<user_id>/<resource_id>/<filename>` (a local uploads dir, not the DB). Record a `Resource` row (name, type, file_path, course_id).
2. **Extract passages** — pull text from the PDF (reuse the `ocr-and-documents` pipeline: `pdftotext -layout` first, markitdown, etc.). Split into chunks (overlapping ~500-token passages). Each chunk becomes a `Passage` row (`content`, `index_order`) under the Resource.

**Topic tagging (no vectors):** after extraction, passages are categorized under the module's topics by `tag_passages_to_topics` and stored with `topic_id` set. All downstream grounding (quiz generation, grading context) is plain SQL on `topic_id` — deliberately no embedding index.

**Storage:** `resources` + `passages` (exist). New: a `storage/` dir for the raw files (not tracked in DB beyond `file_path`).

**Endpoints to ADD:**
- `POST /api/courses/{id}/resources` — multipart upload → saves file, creates Resource, kicks off extraction (background) → returns Resource
- `GET /api/resources/{id}/passages` — exists, returns the chunked passages
- `POST /api/resources/{id}/extract` — (optional) re-run extraction

**Frontend:** upload dropzone on Course screen → progress indicator → passage list viewer (read the extracted text, verify chunking).

**Fit:** This is the entry point for the whole "knowledge" half. Without it there's nothing to quiz *from* or match against. Passages feed question-generation (Feature 4) and passage-matching (Feature 5).

---

## Feature 2: Proficiency display + manual override

**What the user does:** On any Topic, sees a "proficiency" bar (0–1). Can see *why* (strengths/weak_points), and manually nudge it ("I actually know this" / "I'm lost").

**Processing:** Proficiency is normally updated automatically by quiz attempts (Feature 3) and study logs (Feature 5). Manual override is a put endpoint. `preferred_method` (visual/reading/practice/mixed) is a user-set hint for later scheduling.

**Storage:** `proficiency` (exists, unique per user+topic).

**Endpoints (exist):**
- `GET /api/users/{id}/proficiency`
- `PUT /api/users/{id}/proficiency/{topic_id}`

**Frontend:** proficiency bar on Topic screen + Course screen (aggregate per-module). Manual override button.

**Fit:** Proficiency is the *single source of truth* the scheduler (Feature 6) reads. Every other feature either writes to it (quiz, study) or reads it (plan). It must be visible and editable first, or nothing downstream makes sense.

---

## Feature 3: Quiz — take, grade, update proficiency

**What the user does:** On a Topic, "Start quiz." Answers questions one at a time (MCQ or short answer). Sees immediate grading + feedback. Finishes → proficiency bar updates.

**Processing:**
1. Pull questions for the topic (`questions` where topic_id). If none exist and AI were wired, generate them (Feature 4).
2. Create an `Assessment` (status in_progress), add its `AssessmentQuestion` rows in order.
3. Each answer → `Attempt` row. Grade: for MCQ, keyword/option match; for short_answer, `ai.evaluate_answer` (stubbed → fallback keyword match on `expected_key_points`).
4. On grade, write back to proficiency via the **exponential running average** (`ALPHA = 0.3`) already implemented in `routers/questions.py`.

**Storage:** `assessments`, `assessment_questions`, `attempts`, `proficiency` (all exist).

**Endpoints (exist, but the attempt-grade is PATCH not POST — frontend must match):**
- `POST /api/assessments` (body: `{user_id}`) — NOTE: no `/users/{id}` prefix
- `POST /api/attempts`, `PATCH /api/attempts/{id}/grade`
- `GET /api/topics/{id}/questions`

**Frontend:** Topic screen gets a "Start quiz" → question flow (one at a time) → grade → score → back to topic with updated proficiency.

**Fit:** The core learning loop. Attempt scores are the primary proficiency signal.

---

## Feature 4: Question Generation (AI) + passage-linked questions

**What the user does:** On a Topic, "Generate questions." Picks count + type (MCQ/short answer). The system generates them grounded in that topic's passages.

**Processing:**
1. Find passages linked to the topic's resources (via `question_passages` join or topic's module's course's resources).
2. Call `ai.generate_questions(topic_description, count, type)` — currently stubbed, returns placeholders. When wired: send passage text as context, get back questions + `expected_key_points` + grounded `passage_id`s.
3. Create `Question` rows, link to passages via `question_passages`.

**Storage:** `questions`, `question_passages` (exist).

**Endpoints (exist):** `POST /api/topics/{id}/generate-questions` (body: `GenerateRequest{count, type}`).

**Frontend:** "Generate" button on Topic → shows generated questions → "add to quiz."

**Fit:** Turns passages into testable material. This is where the AI actually earns its keep — and it's the first feature that needs the LLM wired (currently stubbed).

---

## Feature 5: Study plan / scheduler

**What the user does:** On a "Plan" screen, sees "what to study next" — a list of topics ordered by (low proficiency + high priority + upcoming deadline), each with a suggested duration, mapped to their free slots.

**Processing (the scheduler, currently NOT implemented):**
1. Read `proficiency` (low score = study), `topics.priority` (high = study), `deadlines` (soon + high weight = study), `reviews.due_date` (overdue = study).
2. Score each topic: `need = w1*(1-proficiency) + w2*(priority/5) + w3*(deadline pressure) + w4*(review overdue)`.
3. Read `slots` where type=free, and `preferences` (preferred hours, session length).
4. Emit `Plan` rows: `(slot_id, topic_id, suggested_duration)` sorted by need, respecting session_length.

**Storage:** `plans`, `slots`, `schedules`, `deadlines`, `preferences`, `reviews` (all exist; `reviews` is an SM-2 spaced-repetition table, empty until study logging runs).

**Endpoints to ADD:**
- `POST /api/users/{id}/generate-plan` — runs the scheduler, writes Plan rows, returns them
- `GET /api/users/{id}/plans` — exists, lists plans
- `PATCH /api/plans/{id}` — mark done/skipped (updates status, writes StudyLog + updates Proficiency on "done")

**Frontend:** Plan screen = ordered "study now" list + the free-time calendar it maps to. Marking a plan "done" logs study time (Feature 6).

**Fit:** The payoff feature — turns the raw data into "what should I actually do right now." Needs every earlier feature's data to be meaningful.

---

## Feature 6: Study logging (closes the loop)

**What the user does:** Marks a plan "done" (or manually logs "I studied topic X for 30 min"). Optionally rates confidence after ("I got this" / "still shaky").

**Processing:** Writes a `StudyLog` row (topic, resource/passage if applicable, minutes, confidence_after). On "done," also nudges proficiency up and creates/updates a `Review` (SM-2: next due date + interval + ease).

**Storage:** `study_logs`, `reviews` (exist, currently unused).

**Endpoints to ADD:**
- `POST /api/study-logs` (body: topic_id, minutes, confidence, resource_id?)
- `GET /api/users/{id}/study-logs` (history for "progress" view)

**Frontend:** "done" button on each plan item → logs + nudges proficiency. A "Progress" view shows study history + proficiency over time.

**Fit:** This is the missing entity I flagged in the original schema review — it's what makes proficiency reflect *actual studying*, not just quiz scores. Without it the loop is half-open.

---

## Feature 7: Settings as a real form

**What the user does:** Settings screen with actual inputs — session length (minutes), daily goal (minutes), preferred start/end time — not a JSON editor.

**Processing/Storage:** `preferences` (exists, singleton per user). GET/PUT.

**Endpoints (exist):**
- `GET /api/users/{id}/preference`
- `PUT /api/users/{id}/preference`

**Frontend:** form → PUT on save. Replaces the current raw JSON editor.

**Fit:** Feeds the scheduler (Feature 5).

---

## Feature 8: Deadlines + weight

**What the user does:** Adds a deadline ("DBMS CAT-2", date, weight, linked to a course or topic). Sees upcoming deadlines on dashboard.

**Processing/Storage:** `deadlines` (exists).

**Endpoints (exist):** `POST /api/deadlines`, `GET /api/users/{id}/deadlines`.

**Frontend:** deadline form + dashboard "upcoming" list.

**Fit:** Feeds scheduler pressure score (Feature 5).

---

## Build order (dependency-sequenced)

1. Feature 0 (spine CRUD) — everything hangs off it
2. Feature 7 (settings form) — trivial, unlocks scheduler input
3. Feature 2 (proficiency display) — the read-back
4. Feature 1 (upload → passages) — the knowledge entry point
5. Feature 3 (quiz) — writes proficiency
6. Feature 6 (study logging) — second proficiency signal
7. Feature 8 (deadlines) — scheduler input
8. Feature 5 (scheduler) — reads all of the above
9. Feature 4 (AI question gen) — last, needs LLM wired + passages

Features 4's AI and 5's scheduler are the only ones with *new* logic; the rest are CRUD + wiring to existing tables.
