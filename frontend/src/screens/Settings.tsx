import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  Check,
  Clock,
  Cpu,
  Minus,
  Plus,
  Save,
  Sliders,
  Target,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { Spinner, useFetch, useToastError } from "../hooks";
import {
  USER_ID,
  clearConversations,
  getEngineStatus,
  getPreference,
  getStudyLogs,
  putPreference,
} from "../api";
import { notifyError, notifySuccess } from "../components/notifications";
import ThemeToggle from "../components/ThemeToggle";

const STYLES = [
  { value: "socratic", label: "Socratic", hint: "Leads with questions, never lectures" },
  { value: "balanced", label: "Balanced", hint: "Default TEACH loop" },
  { value: "direct", label: "Direct", hint: "Explains first, then checks" },
  { value: "drill", label: "Exam drill", hint: "Practice over explanation" },
] as const;

const VERBOSITY = [
  { value: "concise", label: "Concise" },
  { value: "balanced", label: "Balanced" },
  { value: "detailed", label: "Detailed" },
] as const;

const DIFFICULTY = [
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
] as const;

const THREADING_LABEL: Record<string, string> = {
  "proxy-sticky": "Sticky threads (local proxy)",
  "stateless": "Stateless (full context each turn)",
  "forced-on": "Threading forced on",
  "forced-off": "Threading forced off",
  "latched-off": "Threading latched off (strict server)",
};

interface FormState {
  session_length_minutes: string;
  daily_goal_minutes: string;
  preferred_start: string;
  preferred_end: string;
  tutor_instructions: string;
  tutor_style: string;
  tutor_verbosity: string;
  default_quiz_count: number;
  default_difficulty: string;
  review_batch_size: number;
}

export default function Settings() {
  const { data: pref, error, loading, reload } = useFetch(() => getPreference(USER_ID));
  useToastError(error);
  const { data: status } = useFetch(() => getEngineStatus().catch(() => null));
  const { data: logs } = useFetch(() => getStudyLogs(USER_ID).catch(() => []));

  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedTick, setSavedTick] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (pref && !form) {
      setForm({
        session_length_minutes: String(pref.session_length_minutes ?? 45),
        daily_goal_minutes: String(pref.daily_goal_minutes ?? 180),
        preferred_start: pref.preferred_start ?? "09:00",
        preferred_end: pref.preferred_end ?? "21:00",
        tutor_instructions: pref.tutor_instructions ?? "",
        tutor_style: pref.tutor_style ?? "balanced",
        tutor_verbosity: pref.tutor_verbosity ?? "balanced",
        default_quiz_count: pref.default_quiz_count ?? 3,
        default_difficulty: pref.default_difficulty ?? "medium",
        review_batch_size: pref.review_batch_size ?? 8,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pref]);

  // Today's studied minutes vs the daily goal — the goal made functional.
  const todayMinutes = useMemo(() => {
    if (!logs) return 0;
    const today = new Date().toDateString();
    return logs.reduce((sum, l) => {
      if (!l.created_at) return sum;
      return new Date(l.created_at).toDateString() === today
        ? sum + (l.minutes_spent || 0)
        : sum;
    }, 0);
  }, [logs]);
  const dailyGoal = form ? Number(form.daily_goal_minutes) || 0 : 0;
  const goalPct = dailyGoal > 0 ? Math.min(100, Math.round((todayMinutes / dailyGoal) * 100)) : 0;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSavedTick(false);
  }

  async function handleSave() {
    if (!form) return;
    setSaving(true);
    try {
      const sessionLength = form.session_length_minutes.trim() ? Number(form.session_length_minutes) : undefined;
      const dailyGoalNum = form.daily_goal_minutes.trim() ? Number(form.daily_goal_minutes) : undefined;
      if ((sessionLength !== undefined && Number.isNaN(sessionLength)) || (dailyGoalNum !== undefined && Number.isNaN(dailyGoalNum))) {
        notifyError("Session length and daily goal must be valid numbers");
        return;
      }
      await putPreference({
        session_length_minutes: sessionLength,
        daily_goal_minutes: dailyGoalNum,
        preferred_start: form.preferred_start.trim() || null,
        preferred_end: form.preferred_end.trim() || null,
        tutor_instructions: form.tutor_instructions.trim() || null,
        tutor_style: form.tutor_style,
        tutor_verbosity: form.tutor_verbosity,
        default_quiz_count: form.default_quiz_count,
        default_difficulty: form.default_difficulty,
        review_batch_size: form.review_batch_size,
      });
      setSavedTick(true);
      setTimeout(() => setSavedTick(false), 4000);
      reload();
    } catch (e) {
      notifyError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleClearChats() {
    if (!confirmClear) {
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 5000);
      return;
    }
    setClearing(true);
    try {
      const res = await clearConversations(USER_ID);
      notifySuccess(`Deleted ${res.deleted} conversation${res.deleted === 1 ? "" : "s"}.`);
      try {
        Object.keys(localStorage)
          .filter((k) => k.startsWith("kb.chat.") || k === "kb.convos" || k === "kb.activeConvo")
          .forEach((k) => localStorage.removeItem(k));
      } catch {
        // best-effort
      }
    } catch (e) {
      notifyError((e as Error).message);
    } finally {
      setClearing(false);
      setConfirmClear(false);
    }
  }

  function stepper(value: number, min: number, max: number, onChange: (v: number) => void) {
    return (
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onChange(Math.max(min, value - 1))}
          disabled={value <= min}
          className="p-1.5 rounded-lg bg-muted/70 border border-border text-foreground hover:border-accent/50 disabled:opacity-40"
        >
          <Minus size={13} />
        </button>
        <span className="text-sm font-mono font-semibold text-foreground w-6 text-center">{value}</span>
        <button
          type="button"
          onClick={() => onChange(Math.min(max, value + 1))}
          disabled={value >= max}
          className="p-1.5 rounded-lg bg-muted/70 border border-border text-foreground hover:border-accent/50 disabled:opacity-40"
        >
          <Plus size={13} />
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl animate-fadeIn">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
        <div>
          <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-1">
            <Sliders size={14} /> Profile & Engine
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
            Preferences
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Tutor behavior, study targets, practice defaults — everything here takes effect
          </p>
        </div>
      </div>

      {(loading || !form) && <Spinner />}

      {!loading && !error && form && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
          <div className="md:col-span-2 space-y-6">
            {/* Tutor */}
            <section className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-4">
              <div className="flex items-center gap-2.5 pb-3 border-b border-border/60">
                <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                  <Bot size={18} />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-foreground leading-tight">Tutor behavior</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Composes your system prompt — takes effect in new chats
                  </p>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground">Teaching style</label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {STYLES.map((s) => (
                    <button
                      key={s.value}
                      type="button"
                      title={s.hint}
                      onClick={() => update("tutor_style", s.value)}
                      className={`px-2 py-2 rounded-lg border text-xs font-semibold transition-colors ${
                        form.tutor_style === s.value
                          ? "bg-accent/15 border-accent/50 text-foreground"
                          : "bg-muted/50 border-border text-muted-foreground hover:text-foreground hover:border-accent/30"
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground">Reply length</label>
                <div className="grid grid-cols-3 gap-2 max-w-xs">
                  {VERBOSITY.map((v) => (
                    <button
                      key={v.value}
                      type="button"
                      onClick={() => update("tutor_verbosity", v.value)}
                      className={`px-2 py-2 rounded-lg border text-xs font-semibold transition-colors ${
                        form.tutor_verbosity === v.value
                          ? "bg-accent/15 border-accent/50 text-foreground"
                          : "bg-muted/50 border-border text-muted-foreground hover:text-foreground hover:border-accent/30"
                      }`}
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground">
                  Custom instructions{" "}
                  <span className="font-normal text-muted-foreground">— highest priority, injected every turn</span>
                </label>
                <textarea
                  value={form.tutor_instructions}
                  onChange={(e) => update("tutor_instructions", e.target.value)}
                  rows={4}
                  placeholder={"e.g. Quiz me with hard questions only.\nExplain like I'm revising the night before the exam."}
                  className="text-xs w-full"
                />
              </div>
            </section>

            {/* Study targets */}
            <section className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-4">
              <div className="flex items-center gap-2.5 pb-3 border-b border-border/60">
                <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                  <Target size={18} />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-foreground leading-tight">Study targets</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Session length feeds the study planner
                  </p>
                </div>
              </div>

              {dailyGoal > 0 && (
                <div className="rounded-xl bg-muted/50 border border-border/60 px-3.5 py-3">
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="font-semibold text-foreground">Today</span>
                    <span className="font-mono text-muted-foreground">
                      {todayMinutes} / {dailyGoal} min
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-card overflow-hidden">
                    <div
                      className="h-full rounded-full bg-accent transition-all"
                      style={{ width: `${goalPct}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Clock size={13} className="text-accent" /> Session length (min)
                  </label>
                  <input
                    type="number" min={5} max={180} step={5}
                    value={form.session_length_minutes}
                    onChange={(e) => update("session_length_minutes", e.target.value)}
                    placeholder="45" className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Target size={13} className="text-emerald-400" /> Daily goal (min)
                  </label>
                  <input
                    type="number" min={10} max={600} step={10}
                    value={form.daily_goal_minutes}
                    onChange={(e) => update("daily_goal_minutes", e.target.value)}
                    placeholder="180" className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Preferred start</label>
                  <input
                    type="time" value={form.preferred_start}
                    onChange={(e) => update("preferred_start", e.target.value)}
                    className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Preferred end</label>
                  <input
                    type="time" value={form.preferred_end}
                    onChange={(e) => update("preferred_end", e.target.value)}
                    className="text-xs font-mono"
                  />
                </div>
              </div>
            </section>

            {/* Practice defaults */}
            <section className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-4">
              <div className="flex items-center gap-2.5 pb-3 border-b border-border/60">
                <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                  <Check size={18} />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-foreground leading-tight">Practice defaults</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Used whenever the tutor doesn't specify otherwise
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Questions / topic</label>
                  {stepper(form.default_quiz_count, 1, 10, (v) => update("default_quiz_count", v))}
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Difficulty</label>
                  <div className="flex gap-1.5">
                    {DIFFICULTY.map((d) => (
                      <button
                        key={d.value}
                        type="button"
                        onClick={() => update("default_difficulty", d.value)}
                        className={`flex-1 px-2 py-2 rounded-lg border text-xs font-semibold transition-colors ${
                          form.default_difficulty === d.value
                            ? "bg-accent/15 border-accent/50 text-foreground"
                            : "bg-muted/50 border-border text-muted-foreground hover:text-foreground hover:border-accent/30"
                        }`}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Review batch</label>
                  {stepper(form.review_batch_size, 1, 15, (v) => update("review_batch_size", v))}
                </div>
              </div>
            </section>

            <div className="flex items-center gap-3">
              <button className="btn text-xs py-2 px-4" disabled={saving} onClick={handleSave}>
                <Save size={14} /> {saving ? "Saving…" : "Save preferences"}
              </button>
              {savedTick && (
                <span className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-950/40 text-emerald-300 border border-emerald-800/40">
                  <Check size={14} /> Saved
                </span>
              )}
            </div>
          </div>

          {/* Rail */}
          <div className="space-y-4">
            <div className="p-5 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-2.5">
              <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider">
                <Cpu size={14} /> Engine
              </div>
              {status ? (
                <div className="pt-1 space-y-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Model</span>
                    <span className="font-mono font-medium text-foreground truncate">{status.model}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Endpoint</span>
                    <span className="font-mono text-muted-foreground truncate" title={status.endpoint}>
                      {status.endpoint.replace(/^https?:\/\//, "")}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Threading</span>
                    <span className="font-medium text-foreground text-right">
                      {THREADING_LABEL[status.threading] ?? status.threading}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Database</span>
                    <span className="font-medium text-emerald-400">{status.database}</span>
                  </div>
                  <div className="pt-2 border-t border-border/60 flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">Library</span>
                    <span className="font-mono text-foreground">
                      {status.courses} courses · {status.topics} topics · {status.conversations} chats
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Engine unreachable.</p>
              )}
            </div>

            <div className="p-5 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-2">
              <h3 className="text-xs font-semibold text-foreground">Appearance</h3>
              <ThemeToggle />
            </div>

            <div className="p-5 rounded-2xl bg-card/60 border border-rose-900/40 shadow-md space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-rose-300">
                <TriangleAlert size={14} /> Danger zone
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Delete all tutor conversations and their messages. Library, quizzes, and progress are kept.
              </p>
              <button
                onClick={handleClearChats}
                disabled={clearing}
                className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg border transition-colors disabled:opacity-50 ${
                  confirmClear
                    ? "bg-rose-950/60 border-rose-700 text-rose-200 hover:bg-rose-900/60"
                    : "bg-muted/50 border-border text-muted-foreground hover:text-rose-300 hover:border-rose-900/60"
                }`}
              >
                <Trash2 size={13} />
                {clearing ? "Deleting…" : confirmClear ? "Click again to confirm" : "Clear all chats"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
