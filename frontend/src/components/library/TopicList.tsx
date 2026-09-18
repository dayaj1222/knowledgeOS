// Right pane of the two-pane tree: topics of the selected module.
import { useCallback, useState } from "react";
import { Trash2, AlertCircle, FileText } from "lucide-react";
import type { Topic } from "../../api";
import { ProficiencyBar, PriorityChip, EmptyState } from "../indicators";

export function TopicList({
  topics,
  proficiencyByTopic,
  onDelete,
}: {
  topics: Topic[];
  proficiencyByTopic: Record<number, number>;
  onDelete: (id: number) => Promise<void>;
}) {
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const handleDelete = useCallback(
    async (id: number) => {
      if (confirmingId !== id) {
        setConfirmingId(id);
        setTimeout(() => setConfirmingId((cur) => (cur === id ? null : cur)), 4000);
        return;
      }
      setBusy(true);
      try {
        await onDelete(id);
      } finally {
        setBusy(false);
        setConfirmingId(null);
      }
    },
    [confirmingId, onDelete]
  );

  if (topics.length === 0) {
    return <EmptyState message="No topics in this module yet." />;
  }

  return (
    <ul className="space-y-1.5 list-none m-0 p-0">
      {topics.map((t) => {
        const isConfirming = confirmingId === t.id;
        const score = proficiencyByTopic[t.id] ?? 0;
        const scorePct = Math.round(score * 100);
        const name = t.name?.trim() || "Untitled topic";

        return (
          <li
            key={t.id}
            className="p-2.5 rounded-xl bg-muted/40 border border-border/60 hover:border-border/80 hover:bg-card/40 transition-all text-xs group space-y-2"
          >
            {/* Line 1: name + delete */}
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="font-medium text-foreground block truncate flex-1 min-w-0 group-hover:text-foreground"
                title={name}
              >
                {name}
              </span>
              <button
                className={`p-1.5 rounded-lg transition-all flex items-center justify-center flex-shrink-0 cursor-pointer ${
                  isConfirming
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40 px-2"
                    : "text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10"
                }`}
                title={isConfirming ? "Click again to permanently delete" : "Delete topic"}
                disabled={busy}
                onClick={() => handleDelete(t.id)}
              >
                {isConfirming ? (
                  <span className="flex items-center gap-1 text-[10px] font-bold">
                    <AlertCircle size={11} /> Confirm
                  </span>
                ) : (
                  <Trash2 size={13} />
                )}
              </button>
            </div>

            {/* Line 2: priority + chunks */}
            <div className="flex items-center gap-2 flex-wrap">
              <PriorityChip priority={t.priority} />
              <span className="text-[10px] text-muted-foreground font-mono flex items-center gap-1">
                <FileText size={10} className="text-muted-foreground" />
                {t.passage_count ?? 0} {t.passage_count === 1 ? "chunk" : "chunks"}
              </span>
            </div>

            {/* Line 3: mastery bar + percent */}
            <div className="flex items-center gap-2">
              <div className="flex-1 min-w-0">
                <ProficiencyBar score={score} />
              </div>
              <span className="text-[10px] text-muted-foreground font-mono flex-shrink-0 tabular-nums">
                {scorePct}%
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

