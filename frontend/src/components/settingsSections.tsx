import type { ReactNode } from "react";
import { Check, Cpu, Minus, Plus, Trash2, TriangleAlert } from "lucide-react";
import ThemeToggle from "./ThemeToggle";

export function SettingsSection({ icon, title, description, children }: { icon: ReactNode; title: string; description: string; children: ReactNode }) {
  return (
    <section className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-4">
      <div className="flex items-center gap-2.5 pb-3 border-b border-border/60">
        <div className="p-2 rounded-xl bg-accent/10 text-accent border border-accent/20">{icon}</div>
        <div>
          <h2 className="text-sm font-bold text-foreground leading-tight">{title}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export function ChoiceButton({ selected, onClick, children, title }: { selected: boolean; onClick: () => void; children: ReactNode; title?: string }) {
  return <button type="button" title={title} onClick={onClick} className={`px-2 py-2 rounded-lg border text-xs font-semibold transition-colors ${selected ? "bg-accent/15 border-accent/50 text-foreground" : "bg-muted/50 border-border text-muted-foreground hover:text-foreground hover:border-accent/30"}`}>{children}</button>;
}

export function NumberStepper({ value, min, max, onChange }: { value: number; min: number; max: number; onChange: (value: number) => void }) {
  return <div className="flex items-center gap-2"><button type="button" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min} className="p-1.5 rounded-lg bg-muted/70 border border-border text-foreground hover:border-accent/50 disabled:opacity-40"><Minus size={13} /></button><span className="text-sm font-mono font-semibold text-foreground w-6 text-center">{value}</span><button type="button" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} className="p-1.5 rounded-lg bg-muted/70 border border-border text-foreground hover:border-accent/50 disabled:opacity-40"><Plus size={13} /></button></div>;
}

export function GoalProgress({ todayMinutes, dailyGoal, goalPct }: { todayMinutes: number; dailyGoal: number; goalPct: number }) {
  if (dailyGoal <= 0) return null;
  return <div className="rounded-xl bg-muted/50 border border-border/60 px-3.5 py-3"><div className="flex items-center justify-between text-xs mb-1.5"><span className="font-semibold text-foreground">Today</span><span className="font-mono text-muted-foreground">{todayMinutes} / {dailyGoal} min</span></div><div className="h-1.5 rounded-full bg-card overflow-hidden"><div className="h-full rounded-full bg-accent transition-all" style={{ width: `${goalPct}%` }} /></div></div>;
}

const THREADING_LABEL: Record<string, string> = { "proxy-sticky": "Sticky threads (local proxy)", stateless: "Stateless (full context each turn)", "forced-on": "Threading forced on", "forced-off": "Threading forced off", "latched-off": "Threading latched off (strict server)" };

export function EngineCard({ status }: { status: { model: string; endpoint: string; threading: string; database: string; courses: number; topics: number; conversations: number } | null | undefined }) {
  return <div className="p-5 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-2.5"><div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider"><Cpu size={14} /> Engine</div>{status ? <div className="pt-1 space-y-2 text-xs"><div className="flex items-center justify-between gap-2"><span className="text-muted-foreground">Model</span><span className="font-mono font-medium text-foreground truncate">{status.model}</span></div><div className="flex items-center justify-between gap-2"><span className="text-muted-foreground">Endpoint</span><span className="font-mono text-muted-foreground truncate" title={status.endpoint}>{status.endpoint.replace(/^https?:\/\//, "")}</span></div><div className="flex items-center justify-between gap-2"><span className="text-muted-foreground">Threading</span><span className="font-medium text-foreground text-right">{THREADING_LABEL[status.threading] ?? status.threading}</span></div><div className="flex items-center justify-between gap-2"><span className="text-muted-foreground">Database</span><span className="font-medium text-emerald-400">{status.database}</span></div><div className="pt-2 border-t border-border/60 flex items-center justify-between gap-2"><span className="text-muted-foreground">Library</span><span className="font-mono text-foreground">{status.courses} courses · {status.topics} topics · {status.conversations} chats</span></div></div> : <p className="text-xs text-muted-foreground">Engine unreachable.</p>}</div>;
}

export function AppearanceCard() { return <div className="p-5 rounded-2xl bg-card/60 border border-border/80 shadow-md space-y-2"><h3 className="text-xs font-semibold text-foreground">Appearance</h3><ThemeToggle /></div>; }

export function DangerZone({ clearing, confirmClear, onClear }: { clearing: boolean; confirmClear: boolean; onClear: () => void }) {
  return <div className="p-5 rounded-2xl bg-card/60 border border-rose-900/40 shadow-md space-y-2"><div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-rose-300"><TriangleAlert size={14} /> Danger zone</div><p className="text-[11px] text-muted-foreground leading-relaxed">Delete all tutor conversations and their messages. Library, quizzes, and progress are kept.</p><button onClick={onClear} disabled={clearing} className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg border transition-colors disabled:opacity-50 ${confirmClear ? "bg-rose-950/60 border-rose-700 text-rose-200 hover:bg-rose-900/60" : "bg-muted/50 border-border text-muted-foreground hover:text-rose-300 hover:border-rose-900/60"}`}><Trash2 size={13} />{clearing ? "Deleting…" : confirmClear ? "Click again to confirm" : "Clear all chats"}</button></div>;
}

export { Check };
