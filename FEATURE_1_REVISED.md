# Feature 1 (REVISED) — Course / Module / Topic CRUD

Revision of the earlier research, fixing three flaws the orchestrator found.

## Decision: flat or nested topics?

**Recommendation: FLAT for v1.** Topics live directly under a module; no `parent_topic_id` nesting.

Why:
- The app's downstream features (proficiency, quiz, scheduler) are all keyed on `topic_id` and don't care about a topic tree. Nesting adds navigation complexity and reparenting-cycle risk for zero functional gain now.
- `parent_topic_id` already exists as a nullable self-FK, so nothing breaks if we simply don't use it in v1. Revisit nesting only if subtopics become a real need (e.g. "OSI Model" → "Data Link Layer").

## Schema changes (argued, with corrected uniqueness fix)

1. **Non-empty names at the app layer** — strip whitespace, reject `""`. (SQLite treats `""` as non-null, so `nullable=False` does NOT prevent empty strings — must be explicit.)

2. **Sibling-name uniqueness via a PARTIAL/EXPRESSION INDEX, not a table constraint.** The earlier proposal of `UniqueConstraint("module_id", "parent_topic_id", "name")` is WRONG in SQLite: NULLs are treated as distinct in UNIQUE constraints, so two flat topics (parent=NULL) with the same name under one module would NOT be caught. The correct SQLite idiom is:

   ```sql
   CREATE UNIQUE INDEX ux_topic_sibling
     ON topics(module_id, COALESCE(parent_topic_id, 0), name);
   ```

   This is a CREATE TABLE via SQLAlchemy `Index(...)` with `func.coalesce`, or a raw DDL in `init_db`. For modules: `CREATE UNIQUE INDEX ux_module_name ON modules(course_id, name)`.

3. **`order_index` uniqueness per parent** — `UniqueConstraint("module_id", "order_index")` on topics, `UniqueConstraint("course_id", "order_index")` on modules. Without it, reorder is a partial-update mess. Auto-assign `max(order_index)+1` on create when not provided.

4. **`ondelete="CASCADE"` on every `topic_id` FK** (Proficiency, Question, Review, StudyLog, Plan, Deadline) and on `Module.topic_id` → `modules.id`. This makes topic/module deletion atomic. Delete must still be guarded (see below), but cascade is the safety net.

5. **`priority` CHECK 1–5 at the DB layer** (Pydantic already does ge/le, belt-and-suspenders).

## Corrected characterization

`parent_topic_id` and `prerequisite_ids` are **not "dead schema"** — `parent_topic_id` has a self-referential FK wired to `children`/`parent` relationships in `models.py`. The accurate statement: these columns are **modeled but not exercised by any endpoint yet**. `prerequisite_ids` is a real JSON list with no validation; `parent_topic_id` is unused in v1's flat design but preserved.

## Prerequisite validation (app layer, enforced in router)

`prerequisite_ids` is a JSON list. On topic create/update, validate:
- every id exists and belongs to a topic in the **same course** (same module tree),
- no self-reference (`id not in prerequisite_ids`),
- no cycle (iterative DFS over the in-scope prereq graph, bounded ~1000 nodes).

## Endpoint set (full CRUD + reorder)

**Courses**
- `POST /api/users/{user_id}/courses` — validate type ∈ {TH,ETH,ELA}, non-empty name/code, reject duplicate (`user_id`, `code`).
- `GET /api/users/{user_id}/courses?include_counts=true` — return `module_count`, `topic_count` (aggregated, no N+1).
- `PATCH /api/courses/{course_id}` — allow name, code, credits, instructor, type.
- `DELETE /api/courses/{course_id}` — cascade; 409 if any deadline has a future due_date (protect user data), else 204.

**Modules**
- `POST /api/courses/{course_id}/modules` — reject duplicate name per course; auto order_index.
- `GET /api/courses/{course_id}/modules` — embed `topic_count` per module (single query).
- `PATCH /api/modules/{module_id}` — rename / reorder.
- `DELETE /api/modules/{module_id}` — cascade topics; 409 if a topic has questions/reviews and `?force=true` absent.
- `PUT /api/courses/{course_id}/modules/reorder` — body `{module_ids:[...]}`, validate exact set match, rewrite order_index in one transaction.

**Topics**
- `POST /api/topics` — validate module exists, non-empty unique sibling name, priority 1–5, prerequisites (scope/self/cycle checks), auto order_index.
- `GET /api/modules/{module_id}/topics` — flat list + resolved prerequisite names.
- `PATCH /api/topics/{topic_id}` — rename, reprioritize, description, prerequisites (re-run validation).
- `DELETE /api/topics/{topic_id}` — **block (409) if** any Question/Review/StudyLog/Plan/non-cancelled Proficiency references it; `?force=true` to cascade.
- `PUT /api/modules/{module_id}/topics/reorder` — like modules.

## Scale notes

- Dashboard uses `?include_counts=true` — one round trip, never fetch topics per module.
- Topic listing returns the module's topics in one query; build any tree in memory only if nesting returns later.

## Remaining product questions for the user

1. Priority direction — is 5 "most important" or 1? (Only affects how the scheduler weights it; pick one and document.)
2. Confirm FLAT (recommended) vs nested topics for v1.
