import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  Check,
  Clock,
  Save,
  Sliders,
  Target,
} from "lucide-react";
import { Spinner, useFetch, useToastError } from "../hooks";
import {
  USER_ID,
  clearConversations,
  getEngineStatus,
  getPreference,
  getStudyLogs,
  getSystemPrompt,
  putPreference,
} from "../api";
import { notifyError, notifySuccess } from "../components/notifications";
import {
  AppearanceCard,
  ChoiceButton,
  DangerZone,
  EngineCard,
  GoalProgress,
  NumberStepper,
  SettingsSection,
} from "../components/settingsSections";

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
  const [systemPrompt, setSystemPrompt] = useState<string | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);

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

  async function loadSystemPrompt() {
    setPromptLoading(true);
    try {
      const res = await getSystemPrompt(USER_ID);
      setSystemPrompt(res.system_prompt);
    } catch (e) {
      notifyError((e as Error).message);
    } finally {
      setPromptLoading(false);
    }
  }

  useEffect(() => {
    loadSystemPrompt();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      loadSystemPrompt();
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
            <SettingsSection icon={<Bot size={18} />} title="Tutor behavior" description="Composes your system prompt — takes effect in new chats">

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground">Teaching style</label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {STYLES.map((s) => (
                    <ChoiceButton key={s.value} title={s.hint} selected={form.tutor_style === s.value} onClick={() => update("tutor_style", s.value)}>{s.label}</ChoiceButton>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground">Reply length</label>
                <div className="grid grid-cols-3 gap-2 max-w-xs">
                  {VERBOSITY.map((v) => (
                    <ChoiceButton key={v.value} selected={form.tutor_verbosity === v.value} onClick={() => update("tutor_verbosity", v.value)}>{v.label}</ChoiceButton>
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

              <div className="space-y-1.5 pt-3 border-t border-border/60">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-foreground">
                    Actual system prompt{" "}
                    <span className="font-normal text-muted-foreground">— exactly what the model receives</span>
                  </label>
                  <button
                    type="button"
                    onClick={loadSystemPrompt}
                    disabled={promptLoading}
                    className="text-[11px] font-semibold text-accent hover:underline disabled:opacity-50"
                  >
                    {promptLoading ? "Loading…" : "Refresh"}
                  </button>
                </div>
                {systemPrompt ? (
                  <pre className="text-[11px] leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto rounded-xl bg-black/30 border border-border/60 p-3.5 text-muted-foreground font-mono">
                    {systemPrompt}
                  </pre>
                ) : (
                  <p className="text-[11px] text-muted-foreground">
                    {promptLoading ? "Loading the resolved prompt…" : "Could not load the system prompt."}
                  </p>
                )}
              </div>
            </SettingsSection>

            {/* Study targets */}
            <SettingsSection icon={<Target size={18} />} title="Study targets" description="Session length feeds the study planner">

              <GoalProgress todayMinutes={todayMinutes} dailyGoal={dailyGoal} goalPct={goalPct} />

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
            </SettingsSection>

            {/* Practice defaults */}
            <SettingsSection icon={<Check size={18} />} title="Practice defaults" description="Used whenever the tutor doesn't specify otherwise">

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Questions / topic</label>
                  <NumberStepper value={form.default_quiz_count} min={1} max={10} onChange={(v) => update("default_quiz_count", v)} />
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
                  <NumberStepper value={form.review_batch_size} min={1} max={15} onChange={(v) => update("review_batch_size", v)} />
                </div>
              </div>
            </SettingsSection>

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
            <EngineCard status={status} />
            <AppearanceCard />
            <DangerZone clearing={clearing} confirmClear={confirmClear} onClear={handleClearChats} />
          </div>
        </div>
      )}
    </div>
  );
}
