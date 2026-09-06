// Expandable passage viewer: shows the actual chunked text stored for a
// resource, with page provenance, the tagged topic, and tutor/learner notes.

import { useEffect, useState } from "react";
import { FileSearch, Plus, StickyNote, Trash2, X } from "lucide-react";
import {
  addPassageNote,
  deletePassageNote,
  getPassageNotes,
  getPassages,
  type Passage,
  type PassageNote,
} from "../../api";
import { Spinner } from "../../hooks";
import { notifyError } from "../notifications";

function PassageNotes({ passageId }: { passageId: number }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState<PassageNote[] | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || notes !== null) return;
    let cancelled = false;
    getPassageNotes(passageId)
      .then((n) => {
        if (!cancelled) setNotes(n);
      })
      .catch((e) => {
        if (!cancelled) notifyError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [open, notes, passageId]);

  async function save() {
    const text = draft.trim();
    if (!text || saving) return;
    setSaving(true);
    try {
      const created = await addPassageNote(passageId, text);
      setNotes((ns) => [...(ns ?? []), created]);
      setDraft("");
    } catch (e) {
      notifyError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number) {
    try {
      await deletePassageNote(id);
      setNotes((ns) => (ns ?? []).filter((n) => n.id !== id));
    } catch (e) {
      notifyError((e as Error).message);
    }
  }

  return (
    <div className="border-t border-border/60">
      <button
        onClick={() => setOpen((o) => !o)}
        title="Tutor notes on this passage"
        className="flex items-center gap-1.5 w-full px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
      >
        <StickyNote size={11} className={open ? "text-accent" : ""} />
        Notes{notes !== null && notes.length > 0 ? ` (${notes.length})` : ""}
        <span className="ml-auto">{open ? <X size={11} /> : <Plus size={11} />}</span>
      </button>
      {open && (
        <div className="px-2.5 pb-2.5 space-y-1.5">
          {notes === null ? (
            <div className="py-1 flex justify-center">
              <Spinner />
            </div>
          ) : notes.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">
              No notes yet — clarifications you or the tutor save here stick to this passage.
            </p>
          ) : (
            notes.map((n) => (
              <div
                key={n.id}
                className="group flex items-start gap-1.5 rounded-md bg-accent/5 border border-accent/20 px-2 py-1.5 text-[11px] leading-relaxed text-foreground/90"
              >
                <span className="flex-1 whitespace-pre-wrap break-words">{n.note}</span>
                <button
                  title="Delete note"
                  onClick={() => remove(n.id)}
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-muted-foreground hover:text-rose-400 shrink-0"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))
          )}
          <div className="flex items-center gap-1.5">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") save();
              }}
              placeholder="Add a clarification…"
              className="flex-1 text-[11px] rounded-md bg-muted/50 border border-border/70 px-2 py-1.5 text-foreground placeholder:text-muted-foreground/60 focus:border-accent/60"
            />
            <button
              onClick={save}
              disabled={!draft.trim() || saving}
              className="text-[11px] font-semibold px-2.5 py-1.5 rounded-md bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function PassageViewer({
  resourceId,
  topicNameById,
}: {
  resourceId: number;
  topicNameById: Record<number, string>;
}) {
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPassages(resourceId)
      .then((p) => {
        if (!cancelled) setPassages(p);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [resourceId]);

  if (error) {
    return <p className="text-xs text-rose-400 py-2">Couldn't load passages: {error}</p>;
  }
  if (!passages) {
    return (
      <div className="py-3 flex justify-center">
        <Spinner />
      </div>
    );
  }
  if (passages.length === 0) {
    return (
      <div className="py-3 text-center">
        <p className="text-xs text-muted-foreground">No passages extracted yet.</p>
      </div>
    );
  }

  return (
    <ol className="list-none m-0 p-0 space-y-2">
      {passages.map((p) => (
        <li key={p.id} className="rounded-lg bg-muted/50 border border-border/60 overflow-hidden">
          <div className="flex items-center gap-2 px-2.5 py-1.5 border-b border-border/60 text-[10px] font-mono text-muted-foreground">
            <span className="font-bold text-foreground">#{p.index_order + 1}</span>
            {p.page_start != null && (
              <span>
                p.{p.page_start}
                {p.page_end != null && p.page_end !== p.page_start ? `–${p.page_end}` : ""}
              </span>
            )}
            {p.topic_id != null && topicNameById[p.topic_id] && (
              <span className="ml-auto px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/20 font-sans font-semibold truncate max-w-[140px]">
                {topicNameById[p.topic_id]}
              </span>
            )}
          </div>
          <p className="px-2.5 py-2 text-xs leading-relaxed text-foreground/90 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
            {p.content}
          </p>
          <PassageNotes passageId={p.id} />
        </li>
      ))}
    </ol>
  );
}

export function EmptyPassageHint() {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <FileSearch size={12} /> Expand a file to read its passages
    </div>
  );
}
