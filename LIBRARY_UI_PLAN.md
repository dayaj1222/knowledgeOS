# Library UI/UX Redesign — Plan

## Approved decisions
- **Module/topic area**: two-pane tree — module list (left) → topics of selected module (right).
- **Mass import**: multi-file select in file picker + dropzone, concurrent uploads via a queue.
- **Backend**: loop the existing single-upload endpoint (`POST /api/courses/{id}/resources`) from the frontend. No backend change. Zip support deferred.

## Target layout (three columns)
```
┌─────────────┬──────────────────────────┬───────────────────────┐
│  Sidebar    │   Module / Topic tree    │   Context / Materials │
│  courses    │   (two-pane tree)        │   (right rail)        │
│  240px      │   flex 1                 │   360px               │
└─────────────┴──────────────────────────┴───────────────────────┘
```

### Column 1 — Course sidebar
- Collapse "new course" into a `+ New course` AddButton (not always-on inputs).
- Per-course progress ring (from proficiency). Hover `⋯` menu for rename/delete.

### Column 2 — Two-pane tree (the spine)
- Left sub-pane: module list (sticky, compact rows). Select a module.
- Right sub-pane: topics of selected module (dense list).
  - Row: name, priority chip, proficiency bar, passage-count badge, `⋯` menu.
- Add module / add topic as pinned AddButtons in pane headers.

### Column 3 — Context rail (materials)
- Dropzone (multi-file) → upload queue card (per-file status).
- Syllabus upload (secondary action; populates the tree in column 2).
- Resource list with status + view-passages expander.

## Build order
1. Layout shell — three-column grid; move MaterialsPanel to right rail.
2. Two-pane tree — replace flat ModuleCard stack with module-list + topic-list panes.
3. Multi-file dropzone + queue — loop single-upload endpoint, 3 concurrent, live status.
4. Polish — progress rings, `⋯` menus, replace window.confirm with notification system.

## Backend
No changes. Multi-file import uses `uploadResource` per file, bounded concurrency.
