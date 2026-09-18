// In-chat spaced-repetition session: flip cards (recall prompt → key
// points), self-rated per card straight into the SM-2 schedule via the
// existing /reviews/result endpoint. No tutor debrief turn — self-ratings
// need no interpretation; the tutor sees updated schedules next turn.
//
// Progress stashes in localStorage (kb.review.{messageId}) so a reload
// restores the session; the stash clears on finish.

import { useEffect, useRef, useState } from "react";
import { Check, Eye, Layers } from "lucide-react";
import {
  USER_ID,
  cardPayload,
  finishReviewSession,
  submitReviewResult,
  type ChatMessage,
  type ReviewItem,
} from "../api";
import { notifyError } from "./notifications";

const LS_REVIEW = (messageId: number) => `kb.review.${messageId}`;

// SM-2 quality mapping for the three self-ratings.
const RATINGS = [
  { label: "Forgot", quality: 1, hint: "Couldn't recall it" },
  { label: "Shaky", quality: 3, hint: "Partial recall" },
  { label: "Knew it", quality: 5, hint: "Solid recall" },
] as const;

interface ReviewDraft {
  index: number;
  rated: number[];
}

function readDraft(messageId: number): ReviewDraft | null {
  try {
    const raw = localStorage.getItem(LS_REVIEW(messageId));
    return raw ? (JSON.parse(raw) as ReviewDraft) : null;
  } catch {
    return null;
  }
}

export default function InlineReview({ message, conversationId }: { message: ChatMessage; conversationId: number }) {
  const args = (cardPayload(message)) as {
    message_id?: number;
    items?: ReviewItem[];
    completed?: boolean;
  };
  const items = args.items ?? [];
  const messageId = args.message_id ?? message.id;
  // Server-stamped completion survives cache clears and other devices;
  // the localStorage draft only covers the in-progress session.
  const serverDone = args.completed === true;

  const [draft, setDraft] = useState<ReviewDraft>(
    () => readDraft(messageId) ?? { index: 0, rated: [] }
  );
  const [index, setIndex] = useState(() => readDraft(messageId)?.index ?? 0);
  const [revealed, setRevealed] = useState(false);
  const [saving, setSaving] = useState(false);
  const localDone = draft.rated.length >= items.length && items.length > 0;
  const done = serverDone || localDone;

  // First time the session completes locally, stamp it server-side so the
  // card renders done on reloads and other devices (and can't be re-rated
  // into duplicate SM-2 writes). Best-effort: local state already covers
  // this client.
  const finishSent = useRef(serverDone);
  useEffect(() => {
    if (done && !finishSent.current) {
      finishSent.current = true;
      finishReviewSession(conversationId, messageId).catch(() => {
        finishSent.current = false;
      });
    }
  }, [done, conversationId, messageId]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_REVIEW(messageId), JSON.stringify({ ...draft, index }));
    } catch {
      // best-effort
    }
  }, [draft, index, messageId]);

  // Session finished → drop the stash.
  useEffect(() => {
    if (done) {
      try {
        localStorage.removeItem(LS_REVIEW(messageId));
      } catch {
        // best-effort
      }
    }
  }, [done, messageId]);

  if (items.length === 0) return null;
  const item = done ? null : items[Math.min(index, items.length - 1)];

  async function rate(quality: number) {
    if (!item || saving) return;
    setSaving(true);
    try {
      await submitReviewResult({ user_id: USER_ID, topic_id: item.topic_id, quality });
    } catch (e) {
      notifyError((e as Error).message);
      setSaving(false);
      return;
    }
    const rated = [...draft.rated, quality];
    const next = Math.min(index + 1, items.length - 1);
    setDraft({ index: next, rated });
    setIndex(next);
    setRevealed(false);
    setSaving(false);
  }

  if (done) {
    const knew = draft.rated.filter((q) => q >= 5).length;
    return (
      <div className="py-2 text-center space-y-1.5">
        <Check size={20} className="mx-auto text-accent" />
        <p className="text-sm font-semibold text-foreground">Review complete</p>
        <p className="text-xs text-muted-foreground">
          {draft.rated.length > 0
            ? `${items.length} recalled · ${knew} solid — schedules updated.`
            : "Session finished — schedules updated."}
        </p>
      </div>
    );
  }
  if (!item) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Layers size={13} className="text-accent" />
        <span className="font-semibold text-foreground">Recall {index + 1}/{items.length}</span>
        <span className="truncate">· {item.topic_name}</span>
      </div>

      <p className="text-sm font-medium text-foreground leading-relaxed">{item.prompt}</p>

      {!revealed ? (
        <button
          onClick={() => setRevealed(true)}
          className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25 transition-colors"
        >
          <Eye size={13} /> Try to recall, then reveal
        </button>
      ) : (
        <div className="space-y-3 animate-fadeIn">
          <ul className="space-y-1.5 rounded-lg bg-card border border-border p-3">
            {item.key_points.map((k, i) => (
              <li key={i} className="text-[13px] text-foreground flex gap-2">
                <Check size={13} className="text-accent shrink-0 mt-0.5" />
                <span>{k}</span>
              </li>
            ))}
          </ul>
          <div>
            <p className="text-xs text-muted-foreground mb-1.5">How well did you recall it?</p>
            <div className="flex gap-2">
              {RATINGS.map((r) => (
                <button
                  key={r.label}
                  onClick={() => rate(r.quality)}
                  disabled={saving}
                  title={r.hint}
                  className="flex-1 text-xs font-semibold px-2 py-2 rounded-lg bg-muted/70 border border-border text-foreground hover:border-accent/50 hover:bg-accent/10 transition-colors disabled:opacity-50"
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
