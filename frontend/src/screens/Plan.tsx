import { useState } from "react";
import {
  CalendarDays,
  Clock,
  Plus,
  Calendar,
  Clock3,
  CalendarCheck,
} from "lucide-react";
import { getPlans, getDeadlines, createDeadline, USER_ID } from "../api";
import type { Plan, Deadline } from "../api";
import { useFetch, Spinner, useToastError } from "../hooks";
import { notifyError } from "../components/notifications";
import { EmptyState } from "../components/indicators";

export default function PlanScreen() {
  const plans = useFetch(() => getPlans());
  const deadlines = useFetch(() => getDeadlines());
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [weight, setWeight] = useState(15);
  const [saved, setSaved] = useState<{ ok: boolean; msg: string } | null>(null);
  const [adding, setAdding] = useState(false);
  useToastError(plans.error);
  useToastError(deadlines.error);

  async function addDeadline(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !date.trim()) return;
    setAdding(true);
    try {
      await createDeadline({
        user_id: USER_ID,
        course_id: 0,
        title: title.trim(),
        due_date: date.trim(),
        weight: Number(weight) || 10,
      });
      setTitle("");
      setDate("");
      setSaved({ ok: true, msg: "Deadline successfully added to study schedule" });
      deadlines.reload();
      setTimeout(() => setSaved(null), 4000);
    } catch (e) {
      notifyError((e as Error).message);
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
        <div>
          <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-1">
            <CalendarCheck size={14} /> Schedule & Milestones
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
            Study Planner
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Automated revision sessions and academic milestone tracking
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="px-3 py-1.5 rounded-xl bg-card/80 border border-border text-xs text-foreground flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>Smart Scheduler Active</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left 7 Columns: Today's Adaptive Plan */}
        <div className="lg:col-span-7 space-y-6">
          <div className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md backdrop-blur-sm space-y-4">
            <div className="flex items-center justify-between pb-1">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">
                  <Clock size={18} />
                </div>
                <div>
                  <h2 className="text-base font-bold text-foreground leading-tight">
                    Today's Study Blocks
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Recommended topics organized for optimal interval spacing
                  </p>
                </div>
              </div>
              <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-accent/10 text-accent border border-accent/20 font-semibold">
                {plans.data?.length ?? 0} Sessions
              </span>
            </div>

            {plans.loading && <Spinner />}

            {plans.data && plans.data.length === 0 && (
              <EmptyState
                message="No study blocks generated yet. Sessions will appear as topics and deadlines are tracked."
              />
            )}

            {plans.data && plans.data.length > 0 && (
              <div className="space-y-3">
                {plans.data.map((p: Plan, index: number) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between p-4 rounded-xl bg-muted/50 border border-border/70 hover:border-accent/30 transition-all text-xs group"
                  >
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-primary/15 border border-accent/30 flex items-center justify-center text-accent font-mono font-bold flex-shrink-0">
                        {index + 1}
                      </div>
                      <div className="min-w-0">
                        <div className="font-semibold text-sm text-foreground truncate group-hover:text-foreground">
                          Topic Review #{p.topic_id}
                        </div>
                        <div className="text-[11px] text-muted-foreground flex items-center gap-2 mt-0.5">
                          <span className="flex items-center gap-1">
                            <Clock3 size={11} className="text-muted-foreground" />
                            {p.suggested_duration_minutes} minutes
                          </span>
                          <span className="w-1 h-1 rounded-full bg-muted" />
                          <span>Generated {p.generated_at ? new Date(p.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "today"}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2.5 flex-shrink-0">
                      <span className="chip success uppercase text-[10px] font-bold">
                        {p.status || "Scheduled"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Strategy Advice Card */}
          <div className="p-5 rounded-2xl bg-card/60 border border-border/80 shadow-md">
            <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-1.5">
              <Clock size={14} /> Focus Timing Recommendation
            </div>
            <p className="text-xs text-foreground leading-relaxed">
              Based on your preference settings (default 45-minute focus intervals), schedule deep focus blocks with 10-minute breaks between quiz sessions to maximize concentration.
            </p>
          </div>
        </div>

        {/* Right 5 Columns: Deadlines & Quick Add Form */}
        <div className="lg:col-span-5 space-y-6">
          <div className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md backdrop-blur-sm space-y-4">
            <div className="flex items-center justify-between pb-1">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <CalendarDays size={18} />
                </div>
                <div>
                  <h2 className="text-base font-bold text-foreground leading-tight">
                    Academic Deadlines
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Exams, assignments & milestones
                  </p>
                </div>
              </div>
              <span className="text-xs font-mono px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20 font-semibold">
                {deadlines.data?.length ?? 0}
              </span>
            </div>

            {deadlines.loading && <Spinner />}

            {deadlines.data && deadlines.data.length === 0 && (
              <EmptyState message="No deadlines scheduled yet." />
            )}

            {deadlines.data && deadlines.data.length > 0 && (
              <div className="space-y-2.5 max-h-72 overflow-y-auto pr-0.5">
                {deadlines.data.map((d: Deadline) => (
                  <div
                    key={d.id}
                    className="p-3.5 rounded-xl bg-muted/50 border border-border/70 hover:border-border transition-colors text-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-sm text-foreground truncate">
                        {d.title}
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-muted text-foreground border border-border/80 flex-shrink-0">
                        Weight {d.weight}%
                      </span>
                    </div>

                    <div className="mt-2 flex items-center justify-between text-muted-foreground text-[11px]">
                      <span className="flex items-center gap-1.5">
                        <Calendar size={12} className="text-accent" />
                        {new Date(d.due_date).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </span>
                      <span className="text-amber-400 font-medium">Active</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Quick Add Deadline Card Form */}
            <form onSubmit={addDeadline} className="pt-4 border-t border-border/70 space-y-3">
              <span className="text-xs font-bold uppercase tracking-wider text-foreground block">
                Schedule New Milestone
              </span>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Title (e.g. Midterm Examination, Lab Report)"
                className="text-xs"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="text-xs"
                />
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={weight}
                  onChange={(e) => setWeight(Number(e.target.value))}
                  placeholder="Weight %"
                  className="text-xs"
                />
              </div>

              <button
                type="submit"
                disabled={adding || !title.trim() || !date.trim()}
                className="btn w-full text-xs py-2"
              >
                <Plus size={14} />
                {adding ? "Saving..." : "Add to Schedule"}
              </button>

              {saved && (
                <div className="p-2.5 rounded-lg text-xs bg-emerald-950/40 text-emerald-300 border border-emerald-800/40">
                  {saved.msg}
                </div>
              )}
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

