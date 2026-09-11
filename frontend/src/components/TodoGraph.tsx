// TodoGraph — side-panel progress graph for the agent todo list.
// Shows only while the active chat has a live plan. Sleek vertical stepper:
// completed (accent check) → in_progress (glowing current phase) → pending.

import { Check, Loader2 } from "lucide-react";
import type { TodoPayload } from "../api";

export default function TodoGraph({ todo }: { todo: TodoPayload }) {
  const pct = todo.total > 0 ? Math.round((todo.completed / todo.total) * 100) : 0;
  return (
    <div className="rounded-2xl bg-card border border-border/70 p-4 shadow-sm space-y-3.5">
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <h2 className="text-xs font-bold tracking-wide text-foreground">Plan</h2>
          <span className="text-[11px] font-mono tabular-nums text-muted-foreground">
            {todo.completed}/{todo.total} · {pct}%
          </span>
        </div>
        <div className="h-1 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-accent/70 to-accent transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {todo.current_active && (
        <div className="flex items-center gap-2 rounded-xl bg-accent/[0.08] border border-accent/25 px-2.5 py-2">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
          </span>
          <p className="text-xs font-medium text-foreground truncate">
            {todo.current_active}
          </p>
        </div>
      )}

      <ol>
        {todo.todos.map((t, i) => {
          const last = i === todo.todos.length - 1;
          const done = t.status === "completed";
          const active = t.status === "in_progress";
          return (
            <li key={i} className="flex gap-2.5">
              <div className="flex flex-col items-center shrink-0">
                {done ? (
                  <span className="mt-0.5 w-[18px] h-[18px] rounded-full bg-accent flex items-center justify-center text-white shadow-sm shadow-accent/40">
                    <Check size={11} strokeWidth={3.5} />
                  </span>
                ) : active ? (
                  <span className="mt-0.5 w-[18px] h-[18px] rounded-full border-2 border-accent flex items-center justify-center bg-accent/10 shadow-[0_0_8px_rgba(0,0,0,0.15)]">
                    <Loader2 size={10} className="animate-spin text-accent" />
                  </span>
                ) : (
                  <span className="mt-[7px] w-2 h-2 rounded-full bg-border" />
                )}
                {!last && (
                  <span
                    className={`w-px flex-1 min-h-3 ${done ? "bg-accent/60" : "bg-border/70"}`}
                  />
                )}
              </div>
              <p
                className={`pb-3.5 text-xs leading-snug ${last ? "!pb-0" : ""} ${
                  done
                    ? "text-muted-foreground/70 line-through"
                    : active
                      ? "text-foreground font-semibold"
                      : "text-muted-foreground"
                }`}
              >
                {active ? t.activeForm || t.content : t.content}
                {t.weight != null && t.weight > 0 && (
                  <span className="ml-1.5 font-mono text-[10px] text-muted-foreground/70">
                    {Math.round(t.weight * 100)}%
                  </span>
                )}
              </p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
