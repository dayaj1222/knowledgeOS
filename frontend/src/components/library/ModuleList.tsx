// Left pane of the two-pane tree: selectable module list.
import { Layers, ChevronRight, MessageCircle } from "lucide-react";
import type { Module, Topic } from "../../api";

export function ModuleList({
  modules,
  topicsByModule,
  selectedModuleId,
  onSelect,
  onStartChat,
}: {
  modules: Module[];
  topicsByModule: Record<number, Topic[]>;
  selectedModuleId: number | null;
  onSelect: (id: number) => void;
  onStartChat?: (m: { id: number; name: string }) => void;
}) {
  if (modules.length === 0) return null;

  return (
    <ul className="space-y-1.5 list-none m-0 p-0">
      {modules.map((m) => {
        const count = topicsByModule[m.id]?.length ?? 0;
        const active = m.id === selectedModuleId;
        return (
          <li key={m.id}>
            <button
              onClick={() => onSelect(m.id)}
              title={m.name}
              className={`w-full text-left p-2.5 rounded-xl transition-all flex items-center justify-between gap-2 border text-xs ${
                active
                  ? "bg-primary/15 border-accent/40 text-foreground font-semibold shadow-xs"
                  : "bg-muted/40 border-border/60 text-foreground hover:border-border hover:bg-card/60 hover:text-foreground"
              }`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div
                  className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 transition-colors ${
                    active
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted/80 text-muted-foreground"
                  }`}
                >
                  <Layers size={13} strokeWidth={active ? 2.2 : 1.8} />
                </div>
                <span className="truncate leading-tight">{m.name}</span>
              </div>

              <div className="flex items-center gap-1.5 flex-shrink-0">
                {onStartChat && (
                  <button
                    type="button"
                    title={`Start a pinned chat about ${m.name}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onStartChat({ id: m.id, name: m.name });
                    }}
                    className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold text-accent bg-accent/10 border border-accent/30 hover:bg-accent/20 cursor-pointer whitespace-nowrap"
                  >
                    <MessageCircle size={11} /> Chat
                  </button>
                )}
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded-full ${
                    active
                      ? "bg-accent/20 text-accent border border-accent/30 font-bold"
                      : "bg-muted/80 text-muted-foreground"
                  }`}
                >
                  {count}
                </span>
                {active && (
                  <ChevronRight size={13} className="text-accent flex-shrink-0" />
                )}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

