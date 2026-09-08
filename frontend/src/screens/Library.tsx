// Library — minimalist three-column layout.
//   Courses | Modules + Topics | Uploads + Materials (expandable passages)

import { useState } from "react";
import {
  Plus,
  FileText,
  ChevronRight,
  ChevronDown,
  FolderOpen,
  BookOpen,
  BookMarked,
  FilePlus2,
  Layers3,
  ListTodo,
} from "lucide-react";
import { useStore, useSelectedCourse } from "../store";
import { EmptyState } from "../components/indicators";
import { notifyError, notifySuccess } from "../components/notifications";
import { Spinner } from "../hooks";
import { CourseListItem } from "../components/library/CourseListItem";
import { ModuleList } from "../components/library/ModuleList";
import { TopicList } from "../components/library/TopicList";
import { MultiUploader } from "../components/library/MultiUploader";
import { AddButton } from "../components/library/AddButton";
import { PassageViewer } from "../components/library/PassageViewer";

export default function Library() {
  const {
    modules,
    topicsByModule,
    resources,
    proficiency,
    loadingTree,
    error,
    addTopic,
    removeTopic,
    addModule,
    uploadMaterialFiles,
    uploadSyllabusFile,
  } = useStore();
  const selectedCourse = useSelectedCourse();
  const [selectedModuleId, setSelectedModuleId] = useState<number | null>(null);
  const [openResourceId, setOpenResourceId] = useState<number | null>(null);

  const activeModuleId = selectedModuleId ?? modules[0]?.id ?? null;
  const activeModule = activeModuleId != null ? modules.find((m) => m.id === activeModuleId) : null;
  const activeTopics = activeModuleId != null ? topicsByModule[activeModuleId] ?? [] : [];

  const proficiencyByTopic: Record<number, number> = {};
  for (const p of proficiency) proficiencyByTopic[p.topic_id] = p.score;

  const moduleNameById: Record<number, string> = {};
  for (const m of modules) moduleNameById[m.id] = m.name;

  const topicNameById: Record<number, string> = {};
  for (const list of Object.values(topicsByModule)) {
    for (const t of list) topicNameById[t.id] = t.name;
  }

  return (
    <div className="space-y-5 animate-fadeIn max-w-6xl">
      {/* Compact header */}
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-foreground tracking-tight flex items-center gap-2">
          <BookMarked size={18} className="text-accent" />
          Library
        </h1>
        {selectedCourse && (
          <span className="text-xs text-muted-foreground font-mono">
            {selectedCourse.code} · {modules.length} modules · {resources.length} files
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Courses */}
        <div className="lg:col-span-3">
          <CourseSidebar />
        </div>

        {/* Modules + Topics */}
        <div className="lg:col-span-5">
          {selectedCourse ? (
            <div className="rounded-xl bg-card border border-border p-4 space-y-3">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground min-w-0">
                <FolderOpen size={13} className="text-accent shrink-0" />
                <span
                  className="hover:text-foreground cursor-pointer truncate"
                  title={selectedCourse.name}
                  onClick={() => setSelectedModuleId(activeModuleId)}
                >
                  {selectedCourse.name}
                </span>
                {activeModule && (
                  <>
                    <ChevronRight size={12} className="shrink-0" />
                    <span className="font-semibold text-foreground truncate" title={activeModule.name}>
                      {activeModule.name}
                    </span>
                  </>
                )}
              </div>

              {error && (
                <div className="p-2.5 rounded-lg bg-rose-950/30 border border-rose-800/50 text-rose-300 text-xs">
                  {error}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                    <Layers3 size={12} className="text-accent" />
                    Modules ({modules.length})
                  </div>
                  {loadingTree ? (
                    <Spinner />
                  ) : (
                    <ModuleList
                      modules={modules}
                      topicsByModule={topicsByModule}
                      selectedModuleId={activeModuleId}
                      onSelect={setSelectedModuleId}
                    />
                  )}
                  <AddButton
                    label="Add module"
                    placeholder="Module title"
                    onAdd={(name) => addModule(selectedCourse.id, name)}
                  />
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                    <ListTodo size={12} className="text-accent" />
                    Topics ({activeTopics.length})
                  </div>
                  {!loadingTree && activeModuleId == null && (
                    <EmptyState message="No modules yet — upload a syllabus or add one." />
                  )}
                  {!loadingTree && activeModuleId != null && (
                    <TopicList
                      topics={activeTopics}
                      proficiencyByTopic={proficiencyByTopic}
                      onDelete={removeTopic}
                    />
                  )}
                  {activeModuleId != null && (
                    <AddButton
                      label="Add topic"
                      placeholder="Topic name"
                      onAdd={(name) => addTopic(activeModuleId, name)}
                    />
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-8 rounded-xl bg-card border border-dashed border-border text-center">
              <BookOpen size={28} className="mx-auto text-muted-foreground mb-2" />
              <h3 className="text-sm font-semibold text-foreground">No course selected</h3>
              <p className="text-xs text-muted-foreground mt-1">
                Pick a course on the left, or create one.
              </p>
            </div>
          )}
        </div>

        {/* Uploads + Materials */}
        <div className="lg:col-span-4 space-y-3">
          {selectedCourse && (
            <>
              <div className="rounded-xl bg-card border border-border p-4 space-y-2.5">
                <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <FilePlus2 size={13} className="text-accent" />
                  Upload materials
                </h3>
                <MultiUploader
                  moduleId={activeModuleId}
                  onUpload={async (files) => {
                    await uploadMaterialFiles(
                      selectedCourse.id,
                      files.map((f) => ({ ...f, moduleId: f.moduleId }))
                    );
                  }}
                />
              </div>

              <div className="rounded-xl bg-card border border-border p-4 space-y-2.5">
                <SyllabusUpload courseId={selectedCourse.id} onUpload={uploadSyllabusFile} />
              </div>

              <div className="rounded-xl bg-card border border-border p-4 space-y-2">
                <h3 className="text-xs font-semibold text-foreground">
                  Files ({resources.length})
                </h3>
                <div className="space-y-1.5 max-h-72 overflow-y-auto pr-0.5">
                  {resources.map((r) => {
                    const open = openResourceId === r.id;
                    return (
                      <div
                        key={r.id}
                        className="rounded-lg bg-muted/50 border border-border/70 text-xs overflow-hidden"
                      >
                        <button
                          onClick={() => setOpenResourceId(open ? null : r.id)}
                          className="w-full flex items-center gap-2 p-2 text-left cursor-pointer"
                        >
                          {open ? (
                            <ChevronDown size={13} className="text-accent shrink-0" />
                          ) : (
                            <ChevronRight size={13} className="text-muted-foreground shrink-0" />
                          )}
                          <FileText size={13} className="text-accent shrink-0" />
                          <span className="flex-1 min-w-0 font-medium text-foreground truncate" title={r.name}>
                            {r.name}
                          </span>
                          <span className="text-[10px] font-mono uppercase font-bold text-muted-foreground shrink-0">
                            {r.status ?? r.type}
                          </span>
                        </button>
                        {open && (
                          <div className="px-2 pb-2">
                            <PassageViewer resourceId={r.id} topicNameById={topicNameById} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {resources.length === 0 && (
                  <p className="text-xs text-muted-foreground text-center py-2">
                    No files yet. Upload above to extract passages.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---- Course Sidebar ---- */

function CourseSidebar() {
  const { courses, selectedCourseId, selectCourse, addCourse } = useStore();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [isAdding, setIsAdding] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !code.trim()) return;
    await addCourse(name.trim(), code.trim());
    setName("");
    setCode("");
    setIsAdding(false);
  }

  return (
    <div className="rounded-xl bg-card border border-border p-3.5 space-y-2.5">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-foreground">
          Courses ({courses.length})
        </h2>
        <button
          onClick={() => setIsAdding(!isAdding)}
          className="text-xs font-semibold text-accent flex items-center gap-1"
        >
          <Plus size={13} /> {isAdding ? "Cancel" : "New"}
        </button>
      </div>

      {isAdding && (
        <form onSubmit={submit} className="rounded-lg bg-muted/60 border border-border space-y-2 p-2.5">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Course name"
            className="text-xs"
            autoFocus
          />
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Code"
            className="text-xs font-mono"
          />
          <button
            type="submit"
            disabled={!name.trim() || !code.trim()}
            className="btn w-full text-xs py-1.5"
          >
            <Plus size={13} /> Create
          </button>
        </form>
      )}

      <ul className="space-y-1.5 max-h-[calc(100vh-260px)] overflow-y-auto pr-0.5 list-none m-0 p-0">
        {courses.map((c) => (
          <CourseListItem
            key={c.id}
            course={c}
            selected={c.id === selectedCourseId}
            onSelect={selectCourse}
          />
        ))}
      </ul>

      {courses.length === 0 && (
        <p className="text-xs text-muted-foreground text-center py-4">No courses yet.</p>
      )}
    </div>
  );
}

/* ---- Syllabus Upload ---- */

function SyllabusUpload({
  courseId,
  onUpload,
}: {
  courseId: number;
  onUpload: (courseId: number, file: File) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      await onUpload(courseId, file);
      notifySuccess("Syllabus parsed into modules and topics.");
      setFile(null);
    } catch (err) {
      notifyError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2.5">
      <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
        <BookOpen size={13} className="text-accent" />
        Syllabus parser
      </h3>
      <form onSubmit={submit} className="space-y-2">
        <input
          type="file"
          accept=".pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-xs file:mr-2 file:py-1 file:px-2.5 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-primary/20 file:text-accent hover:file:bg-primary/30 file:cursor-pointer"
        />
        <button
          type="submit"
          className="btn w-full text-xs py-1.5"
          disabled={busy || !file}
        >
          <BookOpen size={13} />
          {busy ? "Parsing…" : file ? `Build tree from ${file.name}` : "Select syllabus PDF"}
        </button>
      </form>
    </div>
  );
}
