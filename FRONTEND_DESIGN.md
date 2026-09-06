# Knowledge-Base — Frontend Design

Design decisions made against the goal: a usable local-first study tracker where the user uploads material, tracks per-topic proficiency, quizzes themselves, and gets a study plan. Small decisions resolved in favor of that loop.

---

## App shell: sidebar + main area (not top tabs)

Five screens, navigated by a persistent left sidebar. Reason: the app is a "workspace," not a wizard — the user needs to jump between course content and their plan constantly, so persistent nav beats top tabs.

Sidebar (collapsible to icons, Catppuccin Mocha dark, Lucide icons, no emoji):
1. **Dashboard** (home / layouts icon)
2. **Library** (book-open icon) — all courses/materials
3. **Plan** (calendar icon) — what to study now
4. **Quiz** (sparkles / brain icon) — take a quiz
5. **Settings** (settings icon) — real form, not JSON editor

---

## Screen 1 — Dashboard

**Purpose:** one-glance status — what's due, what's weak, what to do next.

**Layout (top to bottom):**
- Header: "Semester 3" + overall progress ring (% of topics with proficiency > threshold).
- **"Study now" card** (the #1 element): the top 3 topics the scheduler recommends, each a row with topic name, course, a 1-bar proficiency meter, and a "Start" button.
- **Upcoming deadlines** list: title, course, due date, days-left chip, weight badge.
- **Recently studied** list: last few StudyLog entries (topic + minutes + confidence).
- "Add course" button (goes to Library with the create form open).

**Buttons:** Start (per topic row), Add course, View all (→ Plan).

---

## Screen 2 — Library

**Purpose:** browse and manage courses/modules/topics/materials. This is the CRUD spine.

**Layout:**
- Left: course list (name, code, progress %). "+ New course" button at top.
- Right: selected course → module tabs → topic list under each module.
- Topic row: name, priority chip (1–5), proficiency bar, prerequisite tags, action buttons (Edit, Delete).

**Material panel** (same screen, below or as a tab within a course):
- "Upload material" button → dropzone/modal: file picker, name, type (pdf/slides/notes).
- Resource list: name, type, passage count, extract status (uploaded/processing/done/failed), "View passages" button.
- Passage viewer: scrollable list of extracted chunks with page ranges.

**Buttons:** + New course, + New module, + New topic (per module), Upload material, Edit, Delete, View passages.

**This is where the current app is missing everything — it has a stub list, not a walkable tree with upload.**

---

## Screen 3 — Plan

**Purpose:** the payoff — "what should I actually do right now."

**Layout:**
- **Today's plan** list: ordered rows (topic, course, suggested duration, slot time) with a "Done" checkbox and "Skip" button.
- **Free-time calendar** (week grid): shows free/class/busy slots; the plan items map onto free slots.
- **Generate plan** button → calls the scheduler → populates today's list.
- Deadline list (shared with Dashboard, editable here).

**Buttons:** Generate plan, Done (per plan item), Skip (per plan item), Add deadline, Edit slot.

---

## Screen 4 — Quiz

**Purpose:** take a quiz, get graded, watch proficiency update.

**Layout:**
- Topic picker: dropdown of topics (or "start from weak topics" shortcut).
- Question view (one at a time): question text, MCQ options (or text area for short answer), Submit button.
- After submit: immediate feedback (correct/incorrect + explanation), Next button.
- End screen: score, per-topic proficiency delta, "Review answers" list.

**Buttons:** Start quiz, Submit, Next, Retake, Back to topic.

**Two flows:** if the topic has no questions, show "Generate questions" button (stub for now); if questions exist, start directly.

---

## Screen 5 — Settings

**Purpose:** real form, not the current raw JSON editor.

**Fields (a form, saved via PUT):**
- Session length (minutes) — number input
- Daily goal (minutes) — number input
- Preferred start time / end time — time inputs
- (read-only) your user profile summary

**Buttons:** Save. One form, one submit, fields map to `Preference` schema.

---

## Cross-cutting design decisions (resolved for the goal)

- **Hardcode `USER_ID = 1`** everywhere until auth exists (matching backend).
- **Catppuccin Mocha** dark: base `#1e1e2e`, surface `#313244`, text `#cdd6f4`, accent `#89b4fa`, green `#a6e3a1`, red `#f38ba8`.
- **Lucide icons only, no emoji.** Map: Dashboard=LayoutDashboard, Library=BookOpen, Plan=CalendarDays, Quiz=Brain (or Sparkles), Settings=Settings.
- **Proficiency bar** = thin horizontal bar, green→red gradient, shows 0–1 score; used on every topic row across screens for consistency.
- **Priority chip** = small colored pill, 1–5; colors: 1=red (low), 5=green (high) — see open question below if direction matters.
- **Empty states** matter more than polish: every list needs "No courses yet — add one" with the action button, or the app feels broken.
- **Loading/error** via a `useFetch` hook + spinner; error shown inline, never silent.

## Remaining consequential decision (only one)

**Priority direction.** The design above assumes **5 = most important** (green). If you want 1 = most important, it's a one-line flip in the chip colors and the scheduler weight. Decide and I'll bake it in.

## File structure (React + Vite + TS)

```
frontend/src/
  api.ts            # typed fetch client (already exists, needs the contract from the design docs)
  App.tsx           # router + sidebar shell
  components/
    Sidebar.tsx
    ProficiencyBar.tsx
    PriorityChip.tsx
    Spinner.tsx
    EmptyState.tsx
  screens/
    Dashboard.tsx
    Library.tsx     # courses + modules + topics + upload + passages
    Plan.tsx
    Quiz.tsx
    Settings.tsx
  hooks.ts          # useFetch
```

## Build order (dependency-sequenced)

1. Sidebar shell + routing (App.tsx) — the frame everything sits in
2. Library (CRUD spine + upload) — Feature 0 + Feature 1's endpoints
3. Dashboard (reads Library's data + proficiency)
4. Quiz (Feature 3)
5. Plan (Feature 5, scheduler)
6. Settings (Feature 7 form)

Each screen is independently buildable; Dashboard depends on Library's data existing, and Plan depends on proficiency + deadlines + slots.
