import { Bookmark } from "lucide-react";

export function ProficiencyBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  return (
    <div className="w-full bg-muted/80 rounded-full h-1.5 overflow-hidden" title={`${Math.round(pct)}% mastery`}>
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{
          width: `${pct}%`,
          background:
            pct >= 75
              ? "linear-gradient(90deg, #10b981 0%, #34d399 100%)"
              : pct >= 40
              ? "linear-gradient(90deg, #6366f1 0%, #818cf8 100%)"
              : "linear-gradient(90deg, #f43f5e 0%, #fb7185 100%)",
        }}
      />
    </div>
  );
}

export function PriorityChip({ priority }: { priority: number }) {
  const isHigh = priority >= 4;
  const isLow = priority <= 2;

  const colorClass = isHigh
    ? "bg-rose-500/15 text-rose-300 border-rose-500/25"
    : isLow
    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/25"
    : "bg-amber-500/15 text-amber-300 border-amber-500/25";

  const label = isHigh ? "High Priority" : isLow ? "Foundation" : "Normal";

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold border ${colorClass}`}
      title={`Priority rating: ${priority}/5`}
    >
      P{priority} · {label}
    </span>
  );
}

export function EmptyState({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <div className="p-8 rounded-2xl border border-dashed border-border/80 bg-muted/30 text-center flex flex-col items-center justify-center space-y-2.5 my-2">
      <div className="w-9 h-9 rounded-xl bg-card border border-border flex items-center justify-center text-muted-foreground">
        <Bookmark size={16} />
      </div>
      <p className="text-xs text-muted-foreground max-w-xs">{message}</p>
      {action}
    </div>
  );
}

