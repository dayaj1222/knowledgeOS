// InlineDemo — self-contained interactive demos from the tutor's show_demo.
// Sandboxed iframe: scripts run, but no same-origin, no network, no parent
// access. Click-to-load so nothing executes before the learner chooses.

import { useState } from "react";
import { FlaskConical, Play } from "lucide-react";
import type { ChatMessage } from "../api";
import { cardPayload } from "../api";

export default function InlineDemo({ message }: { message: ChatMessage }) {
  const [running, setRunning] = useState(false);
  const payload = cardPayload(message) as { title?: string; html?: string; height?: number };
  const html = payload.html ?? "";
  const height = Math.max(200, Math.min(800, payload.height ?? 420));
  if (!html) return null;
  return (
    <div className="rounded-xl overflow-hidden bg-black/40 border border-border/60">
      <div className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-foreground">
        <FlaskConical size={13} className="text-accent shrink-0" />
        <span className="truncate">{payload.title || "Interactive demo"}</span>
      </div>
      {running ? (
        <iframe
          title={payload.title || "Interactive demo"}
          srcDoc={html}
          sandbox="allow-scripts"
          style={{ height }}
          className="w-full bg-white"
        />
      ) : (
        <button
          onClick={() => setRunning(true)}
          className="group relative block w-full text-left"
          title="Run the interactive demo"
        >
          <div
            className="w-full flex items-center justify-center gap-2 text-muted-foreground group-hover:text-foreground transition-colors"
            style={{ height: Math.min(height, 240) }}
          >
            <span className="flex items-center gap-2 text-xs font-semibold px-4 py-2.5 rounded-full bg-accent/15 text-accent border border-accent/30">
              <Play size={13} /> Run demo
            </span>
          </div>
        </button>
      )}
    </div>
  );
}
