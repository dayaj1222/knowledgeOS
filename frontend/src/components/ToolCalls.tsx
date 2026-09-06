// Expandable tool-call transparency: which tools an answer used, with
// arguments and a result preview each. Collapsed to one line by default.

import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import type { ToolCall } from "../api";

function shortArgs(args: unknown): string {
  if (args == null) return "";
  try {
    const s = JSON.stringify(args);
    return s.length > 140 ? s.slice(0, 140) + "…" : s;
  } catch {
    return "";
  }
}

export default function ToolCalls({ calls }: { calls: ToolCall[] }) {
  const [open, setOpen] = useState(false);
  if (!calls || calls.length === 0) return null;
  return (
    <div className="mt-2 mb-1">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-accent/10 border border-accent/20 text-[11px] text-accent hover:bg-accent/20 transition-colors"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Wrench size={11} />
        {calls.length} tool{calls.length === 1 ? "" : "s"}: {calls.map((c) => c.tool).join(", ")}
      </button>
      {open && (
        <ul className="list-none m-0 mt-1 p-0 space-y-1">
          {calls.map((c, i) => (
            <li
              key={`${c.tool}-${i}`}
              className="rounded-md bg-black/20 border border-border/50 px-2 py-1.5 text-[10px] font-mono leading-relaxed"
            >
              <div className="font-bold text-accent">{c.tool}</div>
              {shortArgs(c.args) && <div className="opacity-70 break-all">{shortArgs(c.args)}</div>}
              {c.result_preview && (
                <div className="opacity-60 break-all whitespace-pre-wrap">{c.result_preview}</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
