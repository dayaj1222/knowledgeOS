import { useEffect, useState } from "react";
import {
  Save,
  Check,
  X,
  Sliders,
  Clock,
  Target,
  Sparkles,
  ShieldCheck,
  Sun,
  Moon,
} from "lucide-react";
import { Spinner, useFetch } from "../hooks";
import { getPreference, putPreference, USER_ID } from "../api";
import ThemeToggle from "../components/ThemeToggle";

interface FormState {
  session_length_minutes: string;
  daily_goal_minutes: string;
  preferred_start: string;
  preferred_end: string;
}

const EMPTY: FormState = {
  session_length_minutes: "",
  daily_goal_minutes: "",
  preferred_start: "",
  preferred_end: "",
};

export default function Settings() {
  const { data: pref, error, loading } = useFetch(() => getPreference(USER_ID));

  const [form, setForm] = useState<FormState>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    if (pref) {
      setForm({
        session_length_minutes: String(pref.session_length_minutes ?? "45"),
        daily_goal_minutes: String(pref.daily_goal_minutes ?? "60"),
        preferred_start: pref.preferred_start ?? "09:00",
        preferred_end: pref.preferred_end ?? "21:00",
      });
    }
  }, [pref]);

  function update<K extends keyof FormState>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSaved(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaved(null);
    try {
      const sessionLength = form.session_length_minutes.trim()
        ? Number(form.session_length_minutes)
        : null;
      const dailyGoal = form.daily_goal_minutes.trim()
        ? Number(form.daily_goal_minutes)
        : null;

      if (
        (sessionLength != null && Number.isNaN(sessionLength)) ||
        (dailyGoal != null && Number.isNaN(dailyGoal))
      ) {
        setSaved({ ok: false, message: "Session length and daily goal must be valid numbers" });
        return;
      }

      await putPreference({
        session_length_minutes: sessionLength ?? undefined,
        daily_goal_minutes: dailyGoal ?? undefined,
        preferred_start: form.preferred_start.trim() || null,
        preferred_end: form.preferred_end.trim() || null,
      });
      setSaved({ ok: true, message: "Study preferences saved successfully" });
      setTimeout(() => setSaved(null), 4000);
    } catch (e) {
      setSaved({ ok: false, message: `Failed: ${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 max-w-4xl animate-fadeIn">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
        <div>
          <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-1">
            <Sliders size={14} /> Profile & Optimization
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
            Preferences
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Configure your focus rhythms, daily targets and AI study pacing
          </p>
        </div>
      </div>

      {loading && <Spinner />}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/40 text-rose-300 text-sm">
          Error loading profile: {error}
        </div>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
          {/* Main Configuration Card */}
          <div className="md:col-span-2 p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md backdrop-blur-sm space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-border/60">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                  <Target size={18} />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-foreground leading-tight">
                    Focus & Scheduling Targets
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Used to calculate ideal daily study blocks
                  </p>
                </div>
              </div>
              <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded bg-muted text-foreground">
                User #{USER_ID}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Clock size={13} className="text-accent" />
                  Session Length (Minutes)
                </label>
                <input
                  type="number"
                  min={5}
                  max={180}
                  step={5}
                  value={form.session_length_minutes}
                  onChange={(e) => update("session_length_minutes", e.target.value)}
                  placeholder="45"
                  className="text-xs font-mono"
                />
                <span className="text-[10px] text-muted-foreground block">Recommended: 30 - 60 minutes</span>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Target size={13} className="text-emerald-400" />
                  Daily Goal (Minutes)
                </label>
                <input
                  type="number"
                  min={10}
                  max={600}
                  step={10}
                  value={form.daily_goal_minutes}
                  onChange={(e) => update("daily_goal_minutes", e.target.value)}
                  placeholder="60"
                  className="text-xs font-mono"
                />
                <span className="text-[10px] text-muted-foreground block">Recommended: 60 - 120 minutes</span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Sun size={13} className="text-amber-400" />
                  Preferred Start Window
                </label>
                <input
                  type="time"
                  value={form.preferred_start}
                  onChange={(e) => update("preferred_start", e.target.value)}
                  className="text-xs font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Moon size={13} className="text-accent" />
                  Preferred End Window
                </label>
                <input
                  type="time"
                  value={form.preferred_end}
                  onChange={(e) => update("preferred_end", e.target.value)}
                  className="text-xs font-mono"
                />
              </div>
            </div>

            {/* Appearance & Theme Setting */}
            <div className="pt-4 border-t border-border/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-xs font-semibold text-foreground">Appearance & Theme</h3>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Choose dark, white (light), or synchronize with your operating system
                </p>
              </div>
              <ThemeToggle />
            </div>

            <div className="pt-4 border-t border-border/60 flex items-center justify-between">
              <button
                className="btn text-xs py-2 px-4"
                disabled={saving}
                onClick={handleSave}
              >
                <Save size={14} />
                {saving ? "Saving Changes..." : "Save Preferences"}
              </button>

              {saved && (
                <div
                  className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg ${
                    saved.ok
                      ? "bg-emerald-950/40 text-emerald-300 border border-emerald-800/40"
                      : "bg-rose-950/40 text-rose-300 border border-rose-800/40"
                  }`}
                >
                  {saved.ok ? <Check size={14} /> : <X size={14} />}
                  {saved.message}
                </div>
              )}
            </div>
          </div>

          {/* Profile & Engine Status Rail */}
          <div className="space-y-4">
            <div className="p-5 rounded-2xl bg-card/60 border border-border/80 shadow-md backdrop-blur-sm space-y-3">
              <div className="flex items-center gap-2.5">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-primary to-emerald-400 flex items-center justify-center font-bold text-foreground text-sm">
                  U{USER_ID}
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">Active Student</h3>
                  <p className="text-[11px] text-muted-foreground font-mono">User ID: #{USER_ID}</p>
                </div>
              </div>

              <div className="pt-2 border-t border-border/60 space-y-2 text-xs">
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Engine Model:</span>
                  <span className="text-accent font-mono font-medium">Gemini 2.5 Flash</span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Embeddings:</span>
                  <span className="text-emerald-400 font-mono font-medium">Vector 768d</span>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>Database Sync:</span>
                  <span className="text-foreground font-medium flex items-center gap-1">
                    <ShieldCheck size={13} className="text-emerald-400" /> Connected
                  </span>
                </div>
              </div>
            </div>

            <div className="p-5 rounded-2xl bg-gradient-to-br from-accent/10 via-card/60 to-card/40 border border-accent/20 shadow-md">
              <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-2">
                <Sparkles size={14} /> Adaptive Pacing
              </div>
              <p className="text-xs text-foreground leading-relaxed">
                Your preferred intervals automatically seed the timetable generator and optimize quiz durations to avoid cognitive fatigue.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

