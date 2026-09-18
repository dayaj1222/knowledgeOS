// Expandable tool-call transparency: which tools an answer used, with
// arguments and a result preview each. Collapsed to one line by default.

import { useState } from "react";
import { Check, ChevronDown, ChevronRight, LoaderCircle, Wrench } from "lucide-react";
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
  const names = [...new Set(calls.map((c) => c.tool))];
  return (
    <section
      className="tool-activity mt-3 mb-1 rounded-xl border border-accent/20 bg-accent/[0.045] overflow-hidden"
      aria-label="Tool activity"
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left text-[11px] text-accent hover:bg-accent/10 transition-colors"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Wrench size={12} className="shrink-0" />
        <span className="font-semibold">Tool activity</span>
        <span className="text-accent/60">{calls.length} step{calls.length === 1 ? "" : "s"}</span>
        <span className="ml-auto truncate max-w-[48%] text-[10px] text-accent/70 font-mono">
          {names.join(" · ")}
        </span>
      </button>
      {open && (
        <ul className="list-none m-0 border-t border-accent/15 p-2 space-y-1.5">
          {calls.map((c, i) => (
            <li
              key={`${c.tool}-${i}`}
              className="rounded-lg bg-background/45 border border-border/60 px-2.5 py-2 text-[10px] font-mono leading-relaxed"
            >
              <div className="flex items-center gap-1.5 font-bold text-accent">
                <Check size={11} className="text-green" />
                <span>{c.tool}</span>
              </div>
              {shortArgs(c.args) && <div className="mt-1 opacity-65 break-all">{shortArgs(c.args)}</div>}
              {c.result_preview && (
                <div className="mt-1 border-t border-border/40 pt-1 opacity-60 break-all whitespace-pre-wrap">{c.result_preview}</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ToolActivity({ names }: { names: string[] }) {
  if (names.length === 0) return null;
  return (
    <div className="flex items-center gap-2 rounded-xl border border-accent/20 bg-accent/[0.045] px-3 py-2 text-xs text-accent">
      <LoaderCircle size={13} className="animate-spin shrink-0" />
      <span className="font-medium">Working with your notes</span>
      <span className="truncate text-[10px] font-mono text-accent/70">{names.join(" · ")}</span>
    </div>
  );
}
