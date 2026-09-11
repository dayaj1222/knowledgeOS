// In-chat quiz card: sliding question cards, silent per-card grading, and a
// tutor debrief on finish. Grades/feedback never render here — only the tutor
// sees them (via the hidden debrief turn); the recommendation lands in the
// thread as a normal assistant message.
//
// Draft answers stash in localStorage (kb.quiz.{assessmentId}) so a mid-quiz
// reload restores progress; the stash clears on finish.

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Brain, Check, Clock3, Loader2 } from "lucide-react";
import {
  USER_ID,
  cardPayload,
  createAttempt,
  gradeAttempt,
  type ChatMessage,
  type QuizQuestion,
} from "../api";
import { notifyError } from "./notifications";

const LS_QUIZ = (assessmentId: number) => `kb.quiz.${assessmentId}`;

interface QuizDraft {
  answers: Record<number, string>;
  attemptIds: Record<number, number>;
  gradedAnswers: Record<number, string>;
  index: number;
}

function readDraft(assessmentId: number): QuizDraft | null {
  try {
    const raw = localStorage.getItem(LS_QUIZ(assessmentId));
    return raw ? (JSON.parse(raw) as QuizDraft) : null;
  } catch {
    return null;
  }
}

export default function InlineQuiz({
  message,
  conversationId,
  onFinish,
}: {
  message: ChatMessage;
  conversationId: number;
  onFinish: (conversationId: number, assessmentId: number) => Promise<void>;
}) {
  const args = (cardPayload(message)) as {
    assessment_id?: number;
    questions?: QuizQuestion[];
    completed?: boolean;
  };
  const assessmentId = args.assessment_id ?? 0;
  const questions = args.questions ?? [];
  // Server-stamped on debrief: a finished quiz is read-only (no typing UI).
  // The tutor's note is the thread reply below.
  const [done, setDone] = useState(args.completed === true);

  const [draft, setDraft] = useState<QuizDraft>(
    () => readDraft(assessmentId) ?? { answers: {}, attemptIds: {}, gradedAnswers: {}, index: 0 }
  );
  const [index, setIndex] = useState(() => readDraft(assessmentId)?.index ?? 0);
  const [dir, setDir] = useState<1 | -1>(1);
  // Background grading: advancing never waits for the AI review. Per-question
  // promise chains serialize grades for the same card (no overlapping
  // gradeAttempt calls → no double proficiency fold); only the latest text
  // commits. Refs mirror state for use inside fire-and-forget jobs.
  const attemptIdRef = useRef<Record<number, number>>({ ...draft.attemptIds });
  const gradedRef = useRef<Record<number, string>>({ ...draft.gradedAnswers });
  const creatingRef = useRef<Record<number, Promise<number> | undefined>>({});
  const chainRef = useRef<Record<number, Promise<void>>>({});
  const pendingCount = useRef<Record<number, number>>({});
  const [pending, setPending] = useState<Record<number, boolean>>({});
  const [finishing, setFinishing] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(LS_QUIZ(assessmentId), JSON.stringify({ ...draft, index }));
    } catch {
      // best-effort
    }
  }, [draft, index, assessmentId]);

  if (questions.length === 0) return null;
  const safeIndex = Math.min(index, questions.length - 1);
  const q = questions[safeIndex];
  const isLast = safeIndex === questions.length - 1;
  const answer = draft.answers[q.id] ?? "";
  const busy = finishing || done;

  function markPending(questionId: number, on: boolean) {
    // Counter (not boolean): an older job settling must not clear the flag
    // while a newer job for the same card is still running.
    pendingCount.current[questionId] = Math.max(
      0, (pendingCount.current[questionId] ?? 0) + (on ? 1 : -1)
    );
    const isOn = pendingCount.current[questionId] > 0;
    setPending((p) => {
      if (!!p[questionId] === isOn) return p;
      const next = { ...p };
      if (isOn) next[questionId] = true;
      else delete next[questionId];
      return next;
    });
  }

  /** Grade a card in the background (never awaited by navigation). */
  function fireGrade(questionId: number, text: string): void {
    const trimmed = text.trim();
    if (!trimmed || gradedRef.current[questionId] === trimmed) return; // unchanged — skip
    markPending(questionId, true);
    const run = async (): Promise<void> => {
      try {
        // Skip if a newer answer was fired while this job queued.
        if (gradedRef.current[questionId] === trimmed) return;
        let aid = attemptIdRef.current[questionId];
        if (aid == null) {
          // Serialize creation per question: concurrent advances must not
          // mint duplicate attempts.
          let creating = creatingRef.current[questionId];
          if (!creating) {
            creating = createAttempt({
              user_id: USER_ID,
              assessment_id: assessmentId,
              question_id: questionId,
              user_answer: trimmed,
            }).then((a) => {
              attemptIdRef.current[questionId] = a.id;
              setDraft((d) => ({ ...d, attemptIds: { ...d.attemptIds, [questionId]: a.id } }));
              return a.id;
            });
            creatingRef.current[questionId] = creating;
            creating.catch(() => undefined).finally(() => {
              if (creatingRef.current[questionId] === creating) {
                delete creatingRef.current[questionId];
              }
            });
          }
          aid = await creating;
        }
        // Re-grades the SAME attempt in place so proficiency/SM-2 never
        // double-count card edits.
        await gradeAttempt(aid, { status: "answered", user_answer: trimmed });
        gradedRef.current[questionId] = trimmed;
        setDraft((d) => ({
          ...d,
          gradedAnswers: { ...d.gradedAnswers, [questionId]: trimmed },
        }));
      } catch (e) {
        // Background failure: toast only, card stays usable; Finish retries.
        notifyError(`Grading failed for question — will retry on finish: ${(e as Error).message}`);
      } finally {
        markPending(questionId, false);
      }
    };
    // Chain per question so grades for the same card never overlap.
    chainRef.current[questionId] = (chainRef.current[questionId] ?? Promise.resolve())
      .catch(() => undefined)
      .then(run);
  }

  function advance() {
    if (busy || isLast) return;
    fireGrade(q.id, answer); // background — navigation is instant
    setDir(1);
    setIndex(safeIndex + 1);
  }

  async function finish() {
    if (busy) return;
    setFinishing(true);
    try {
      // Fire grades for anything answered but not yet graded (failed or
      // still in flight), then wait only for what's outstanding.
      for (const qq of questions) {
        fireGrade(qq.id, draft.answers[qq.id] ?? "");
      }
      await Promise.allSettled(Object.values(chainRef.current));
      // One more pass: anything STILL ungraded failed twice — surface it and stop.
      const missing = questions.filter((qq) => {
        const t = (draft.answers[qq.id] ?? "").trim();
        return t !== "" && gradedRef.current[qq.id] !== t;
      });
      if (missing.length > 0) {
        notifyError(
          `Could not grade ${missing.length} answer(s) — finish anyway or retry.`
        );
        return;
      }
      await onFinish(conversationId, assessmentId);
      try {
        localStorage.removeItem(LS_QUIZ(assessmentId));
      } catch {
        // best-effort
      }
      setDone(true);
    } catch (e) {
      notifyError((e as Error).message);
    } finally {
      setFinishing(false);
    }
  }

  if (done) {
    return (
      <div className="flex items-center gap-2.5">
        <span className="w-7 h-7 rounded-lg bg-green/15 text-green border border-green/30 flex items-center justify-center flex-shrink-0">
          <Check size={14} />
        </span>
        <div className="min-w-0">
          <div className="text-xs font-bold text-foreground">Quiz complete</div>
          <div className="text-[11px] text-muted-foreground">
            {questions.length} question{questions.length === 1 ? "" : "s"} · graded and reviewed — see your tutor's note below
          </div>
        </div>
      </div>
    );
  }

  const answeredCount = questions.filter((qq) => (draft.answers[qq.id] ?? "").trim() !== "").length;

  return (
    <div className="space-y-3 min-w-0">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="w-7 h-7 rounded-lg bg-accent/10 text-accent border border-accent/20 flex items-center justify-center flex-shrink-0">
            <Brain size={14} />
          </span>
          <span className="text-xs font-bold text-foreground">Quiz</span>
          <span className="text-[11px] font-mono text-muted-foreground">
            {safeIndex + 1}/{questions.length}
          </span>
        </div>
        <span className="text-[11px] text-accent font-medium">
          {answeredCount} of {questions.length} answered
        </span>
      </div>

      {/* Progress dots */}
      <div className="flex gap-1.5 flex-wrap items-center">
        {questions.map((qq, i) => {
          const graded = draft.attemptIds[qq.id] != null && !pending[qq.id];
          const active = i === safeIndex;
          const gradingBg = pending[qq.id] === true;
          return (
            <button
              key={qq.id}
              disabled={busy}
              onClick={() => {
                setDir(i > safeIndex ? 1 : -1);
                setIndex(i);
              }}
              title={`Question ${i + 1}${graded ? " (submitted)" : ""}`}
              className={`w-7 h-7 rounded-lg font-mono text-[11px] font-bold transition-all flex items-center justify-center border disabled:opacity-60 ${
                active
                  ? "bg-primary text-primary-foreground border-accent scale-105"
                  : graded
                  ? "bg-green/15 text-green border-green/30"
                  : gradingBg
                  ? "bg-accent/10 text-accent border-accent/30 animate-pulse"
                  : "bg-card/60 text-muted-foreground border-border"
              }`}
            >
              {graded && !active ? <Check size={12} /> : gradingBg && !active ? <Loader2 size={12} className="animate-spin" /> : i + 1}
            </button>
          );
        })}
      </div>

      {/* Sliding card */}
      <div
        key={q.id}
        className={dir === 1 ? "quiz-slide-right" : "quiz-slide-left"}
      >
        <div className="flex items-start gap-2">
          <span className="px-1.5 py-0.5 rounded bg-accent/20 text-accent font-mono text-[11px] font-bold mt-0.5 flex-shrink-0">
            Q{safeIndex + 1}
          </span>
          <p className="text-sm font-semibold text-foreground leading-relaxed m-0">
            {q.text}
          </p>
        </div>
        <textarea
          rows={4}
          placeholder="Answer in your own words…"
          value={answer}
          disabled={busy}
          onChange={(e) =>
            setDraft((d) => ({ ...d, answers: { ...d.answers, [q.id]: e.target.value } }))
          }
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              if (isLast) void finish();
              else void advance();
            }
          }}
          className="w-full text-sm leading-relaxed p-3 rounded-xl resize-none mt-2 disabled:opacity-60"
        />
        <div className="flex justify-between items-center text-[11px] text-muted-foreground mt-1.5 px-0.5">
          <span className="flex items-center gap-1">
            <Clock3 size={12} className="text-accent" />
            {draft.attemptIds[q.id] != null
              ? "Submitted — edit and move on to re-grade"
              : "Move on whenever you're ready"}
          </span>
          <span>{answer.split(/\s+/).filter(Boolean).length} words</span>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-1">
        <button
          className="btn-secondary text-xs py-2 px-3.5"
          disabled={safeIndex === 0 || busy}
          onClick={() => {
            setDir(-1);
            setIndex(safeIndex - 1);
          }}
        >
          <ArrowLeft size={13} /> Prev
        </button>
        {isLast ? (
          <button className="btn text-xs py-2 px-5" disabled={busy} onClick={() => void finish()}>
            {finishing ? (
              <><Loader2 size={13} className="animate-spin" /> Handing to your tutor…</>
            ) : (
              <><Check size={13} /> Finish & get feedback</>
            )}
          </button>
        ) : (
          <button className="btn text-xs py-2 px-4" disabled={busy} onClick={advance}>
            Next <ArrowRight size={13} />
          </button>
        )}
      </div>
    </div>
  );
}
