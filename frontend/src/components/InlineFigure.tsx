// InlineFigure — static matplotlib figures from the tutor's plot_chart.
// Plain PNG in a titled frame; stdout (if any) folds below as caption.

import { useState } from "react";
import { ChartLine } from "lucide-react";
import type { ChatMessage } from "../api";
import { cardPayload } from "../api";

export default function InlineFigure({ message }: { message: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const payload = cardPayload(message) as { title?: string; image?: string; stdout?: string };
  if (!payload.image) return null;
  return (
    <div className="rounded-xl overflow-hidden bg-black/40 border border-border/60">
      <div className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-foreground">
        <ChartLine size={13} className="text-accent shrink-0" />
        <span className="truncate">{payload.title || "Figure"}</span>
      </div>
      <button type="button" onClick={() => setOpen(true)} className="block w-full cursor-zoom-in" title="Enlarge">
        <img src={payload.image} alt={payload.title || "Figure"} className="w-full" />
      </button>
      {payload.stdout?.trim() && (
        <pre className="px-3 py-2 text-[11px] font-mono text-muted-foreground whitespace-pre-wrap border-t border-border/60">
          {payload.stdout.trim()}
        </pre>
      )}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6"
          onClick={() => setOpen(false)}
        >
          <img
            src={payload.image}
            alt={payload.title || "Figure"}
            className="max-w-full max-h-full rounded-xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
