// Quiz wizard — a guided creation flow, not a wall of controls.
//
//   Step 1 "Kind":    pick what kind of quiz you want (menu-driven).
//   Step 2 "Setup":   configure only what that kind needs, then generate.
//   Take + Results live on their own routes (/quiz/take, /quiz/results).
//
// Kinds:
//   quick  — 5 questions on your weakest topics (auto-picked).
//   due    — topics whose SM-2 review is due (uses the due queue).
//   gaps   — a drill aimed at your most-missed key points.
//   custom — hand-pick topics + difficulty + focus, the full control.

import { useEffect, useMemo, useState } from "react";
import {
  Zap,
  History,
  Crosshair,
  SlidersHorizontal,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  BookOpen,
  Sparkles,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useStore } from "../../store";
import { useNotify } from "../../components/notifications";
import {
  generateQuiz,
  generateDrill,
  getDueReviews,
  getWeaknesses,
  USER_ID,
  type DueReview,
  type TopicWeakness,
} from "../../api";
import { EmptyState } from "../../components/indicators";

type Kind = "quick" | "due" | "gaps" | "custom";

const DIFFICULTIES = [
  { id: "easy", label: "Foundation", desc: "Recall & definitions" },
  { id: "medium", label: "Intermediate", desc: "Conceptual understanding" },
  { id: "hard", label: "Advanced", desc: "Synthesis & problems" },
];

export default function QuizSetup() {
  const { courses, allCourseTrees, proficiency } = useStore();
  const notify = useNotify();
  const navigate = useNavigate();

  const [step, setStep] = useState<1 | 2>(1);
  const [kind, setKind] = useState<Kind | null>(null);

  // Custom-kind state
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [selectedTopics, setSelectedTopics] = useState<Set<number>>(new Set());

  // Shared params
  const [difficulty, setDifficulty] = useState("medium");
  const [count, setCount] = useState(5);
  const [instructions, setInstructions] = useState("");
  const [generating, setGenerating] = useState(false);

  // Engine-backed context (due queue + diagnosed gaps)
  const [due, setDue] = useState<DueReview[]>([]);
  const [weak, setWeak] = useState<TopicWeakness[]>([]);
  useEffect(() => {
    getDueReviews(USER_ID).then(setDue).catch(() => setDue([]));
    getWeaknesses(USER_ID).then(setWeak).catch(() => setWeak([]));
  }, []);

  const weakTopics = useMemo(
    () =>
      proficiency
        .filter((p) => p.score < 0.7)
        .sort((a, b) => a.score - b.score)
        .slice(0, 5)
        .map((p) => p.topic_id),
    [proficiency]
  );

  const topicName = useMemo(() => {
    const map = new Map<number, string>();
    for (const c of courses) {
      for (const mod of allCourseTrees[c.id] ?? []) {
        for (const t of mod.topics) map.set(t.id, t.name);
      }
    }
    for (const d of due) map.set(d.topic_id, d.topic_name);
    for (const w of weak) map.set(w.topic_id, w.topic_name);
    return map;
  }, [courses, allCourseTrees, due, weak]);

  function chooseKind(k: Kind) {
    setKind(k);
    if (k === "quick") setCount(5);
    if (k === "due") setCount(Math.min(10, Math.max(due.length * 2, 3)));
    if (k === "gaps") setCount(5);
    setStep(2);
  }

  function toggleExpand(id: number) {
    setExpanded((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function toggleTopic(id: number) {
    setSelectedTopics((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function handleGenerate() {
    if (!kind) return;
    setGenerating(true);
    try {
      if (kind === "custom") {
        if (selectedTopics.size === 0) {
          notify.error("Select at least one topic for your quiz.");
          return;
        }
        const qs = await generateQuiz([...selectedTopics], count, difficulty, instructions);
        notify.success(`Generated ${qs.length} questions.`);
        navigate("/quiz/take", { state: { questions: qs } });
        return;
      }
      if (kind === "gaps") {
        const qs = await generateDrill({ user_id: USER_ID, count, difficulty });
        if (qs.length === 0) {
          notify.error("No topics available for a drill yet.");
          return;
        }
        notify.success(`Generated ${qs.length} targeted drill questions.`);
        navigate("/quiz/take", { state: { questions: qs } });
        return;
      }
      const topicIds =
        kind === "quick"
          ? weakTopics
          : [...new Set(due.map((d) => d.topic_id))].slice(0, 5);
      if (topicIds.length === 0) {
        notify.error(
          kind === "quick"
            ? "No weak topics found — take a quiz or log study first."
            : "Nothing is due for review right now."
        );
        return;
      }
      const qs = await generateQuiz(topicIds, count, difficulty, "");
      notify.success(`Generated ${qs.length} questions.`);
      navigate("/quiz/take", { state: { questions: qs } });
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setGenerating(false);
    }
  }

  const autoTopics: { id: number; note?: string }[] =
    kind === "quick"
      ? weakTopics.map((id) => ({ id }))
      : kind === "due"
      ? [...new Map(due.map((d) => [d.topic_id, d])).values()]
          .slice(0, 5)
          .map((d) => ({
            id: d.topic_id,
            note: d.overdue_days > 0 ? `${d.overdue_days}d overdue` : "due today",
          }))
      : kind === "gaps"
      ? weak.slice(0, 3).map((w) => ({ id: w.topic_id, note: `${w.total_missed} misses` }))
      : [];

  const kinds: { id: Kind; title: string; desc: string; icon: React.ReactNode; badge?: string; disabled?: boolean }[] = [
    {
      id: "quick",
      title: "Quick check",
      desc: "5 questions on your weakest topics, auto-picked.",
      icon: <Zap size={18} />,
      badge: weakTopics.length > 0 ? `${weakTopics.length} weak` : undefined,
      disabled: weakTopics.length === 0,
    },
    {
      id: "due",
      title: "Review what's due",
      desc: "Spaced-repetition queue — topics your memory is about to drop.",
      icon: <History size={18} />,
      badge: due.length > 0 ? `${due.length} due` : "clear",
      disabled: due.length === 0,
    },
    {
      id: "gaps",
      title: "Drill my gaps",
      desc: "Questions aimed at the exact key points you keep missing.",
      icon: <Crosshair size={18} />,
      badge: weak.length > 0 ? `${weak.length} topics` : undefined,
      disabled: weak.length === 0,
    },
    {
      id: "custom",
      title: "Custom quiz",
      desc: "Hand-pick topics, difficulty and focus. Full control.",
      icon: <SlidersHorizontal size={18} />,
    },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fadeIn">
      {/* Stepper header */}
      <div className="pb-3 border-b border-border/60">
        <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-1">
          <Sparkles size={14} /> Adaptive Quiz
        </div>
        <h1 className="text-2xl font-extrabold text-foreground tracking-tight">
          {step === 1 ? "What kind of quiz?" : "Configure & generate"}
        </h1>
        <div className="flex items-center gap-2 mt-3">
          {[1, 2].map((s) => (
            <div key={s} className="flex items-center gap-2">
              <span
                className={`w-6 h-6 rounded-full text-[11px] font-bold flex items-center justify-center border transition-colors ${
                  step >= s
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-muted text-muted-foreground border-border"
                }`}
              >
                {s}
              </span>
              <span className={`text-xs font-medium ${step >= s ? "text-foreground" : "text-muted-foreground"}`}>
                {s === 1 ? "Kind" : "Setup"}
              </span>
              {s === 1 && <span className="w-8 h-px bg-border mx-1" />}
            </div>
          ))}
        </div>
      </div>

      {step === 1 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {kinds.map((k) => (
            <button
              key={k.id}
              disabled={k.disabled}
              onClick={() => chooseKind(k.id)}
              className="p-5 rounded-2xl bg-card border border-border text-left transition-all group hover:border-accent/40 hover:bg-card cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-border disabled:hover:bg-card"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="p-2.5 rounded-xl bg-accent/10 text-accent border border-accent/20 group-hover:bg-accent group-hover:text-primary-foreground transition-colors">
                  {k.icon}
                </div>
                {k.badge && (
                  <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border">
                    {k.badge}
                  </span>
                )}
              </div>
              <div className="mt-3 font-bold text-sm text-foreground flex items-center gap-1">
                {k.title}
                <ChevronRight size={14} className="text-muted-foreground group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
              </div>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{k.desc}</p>
            </button>
          ))}
          {courses.length === 0 && (
            <div className="sm:col-span-2">
              <EmptyState message="No courses yet — add one in the Library first." />
            </div>
          )}
        </div>
      )}

      {step === 2 && kind && (
        <div className="space-y-5">
          {/* Resolved topics summary (auto kinds) */}
          {kind !== "custom" && (
            <div className="p-5 rounded-2xl bg-card border border-border space-y-3">
              <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                {kind === "quick" ? "Your weakest topics" : kind === "due" ? "Due for review" : "Biggest gaps"}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {autoTopics.map((t) => (
                  <span
                    key={t.id}
                    className="text-xs px-2.5 py-1 rounded-lg bg-muted text-foreground border border-border font-medium"
                  >
                    {topicName.get(t.id) ?? `Topic #${t.id}`}
                    {t.note && <span className="text-muted-foreground font-mono text-[10px] ml-1.5">{t.note}</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Topic picker (custom kind) */}
          {kind === "custom" && (
            <div className="p-5 rounded-2xl bg-card border border-border space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Pick topics
                </div>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20 font-semibold">
                  {selectedTopics.size} selected
                </span>
              </div>
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                {courses.map((c) => {
                  const tree = allCourseTrees[c.id] ?? [];
                  const open = expanded.has(c.id);
                  const courseTopics = tree.flatMap((m) => m.topics);
                  const n = courseTopics.filter((t) => selectedTopics.has(t.id)).length;
                  return (
                    <div key={c.id} className="rounded-xl border border-border bg-muted/40 overflow-hidden">
                      <button
                        onClick={() => toggleExpand(c.id)}
                        className="w-full flex items-center justify-between p-2.5 text-left hover:bg-muted/60 transition-colors cursor-pointer"
                      >
                        <span className="flex items-center gap-2 min-w-0 text-xs font-semibold text-foreground">
                          {open ? <ChevronDown size={14} className="text-accent shrink-0" /> : <ChevronRight size={14} className="text-muted-foreground shrink-0" />}
                          <BookOpen size={14} className="text-accent shrink-0" />
                          <span className="truncate">{c.name}</span>
                        </span>
                        {n > 0 && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/30">
                            {n}
                          </span>
                        )}
                      </button>
                      {open && (
                        <div className="p-2.5 pt-1 border-t border-border space-y-2">
                          {tree.map((mod) => (
                            <div key={mod.moduleId} className="space-y-1">
                              <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                                {mod.moduleName}
                              </div>
                              {mod.topics.map((t) => {
                                const checked = selectedTopics.has(t.id);
                                return (
                                  <label
                                    key={t.id}
                                    className={`flex items-center gap-2.5 p-2 rounded-lg cursor-pointer text-xs border transition-colors ${
                                      checked
                                        ? "bg-accent/15 border-accent/40 text-foreground font-medium"
                                        : "border-transparent hover:bg-muted/60 text-muted-foreground"
                                    }`}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={() => toggleTopic(t.id)}
                                      className="rounded border-border bg-card text-primary cursor-pointer"
                                    />
                                    <span className="truncate">{t.name}</span>
                                  </label>
                                );
                              })}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Shared params: difficulty + count */}
          <div className="p-5 rounded-2xl bg-card border border-border space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-semibold text-foreground block">Difficulty</label>
              <div className="grid grid-cols-3 gap-2">
                {DIFFICULTIES.map((d) => {
                  const active = difficulty === d.id;
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => setDifficulty(d.id)}
                      className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                        active
                          ? "bg-accent/15 border-accent text-foreground"
                          : "bg-muted/40 border-border text-muted-foreground hover:border-border"
                      }`}
                    >
                      <div className={`text-xs font-bold ${active ? "text-foreground" : "text-accent"}`}>
                        {d.label}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">{d.desc}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-foreground">Questions</label>
                <span className="text-xs font-mono font-bold text-accent">{count}</span>
              </div>
              <input
                type="range"
                min={3}
                max={kind === "custom" ? 25 : 15}
                step={1}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                className="w-full accent-accent cursor-pointer"
              />
            </div>

            {kind === "custom" && (
              <div className="space-y-2">
                <label className="text-xs font-semibold text-foreground block">
                  Focus <span className="text-muted-foreground font-normal">(optional)</span>
                </label>
                <textarea
                  rows={2}
                  placeholder="e.g. edge cases over syntax…"
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  className="text-xs resize-none w-full"
                />
              </div>
            )}
          </div>

          {/* Footer nav */}
          <div className="flex items-center justify-between">
            <button
              className="btn-secondary text-xs py-2.5 px-4"
              onClick={() => setStep(1)}
            >
              <ChevronLeft size={14} /> Back
            </button>
            <button
              className="btn text-xs py-2.5 px-6"
              disabled={generating || (kind === "custom" && selectedTopics.size === 0)}
              onClick={handleGenerate}
            >
              <Sparkles size={14} />
              {generating ? "Generating…" : "Generate & start"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
