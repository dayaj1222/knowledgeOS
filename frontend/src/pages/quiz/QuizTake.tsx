// Quiz take page — one question at a time, with progress bar, question dots,
// and a graded-evaluation progress indicator on submit.

import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Brain,
  ArrowLeft,
  ArrowRight,
  Check,
  Clock3,
  Loader2,
} from "lucide-react";
import { useNotify } from "../../components/notifications";
import {
  createAssessment,
  createAttempt,
  getAssessment,
  gradeAttempt,
  patchAssessment,
  USER_ID,
} from "../../api";
import type { Question } from "../../api";

interface GradedResult {
  text: string;
  score: number;
  feedback: string;
  matched_key_points: string[];
  missed_key_points: string[];
}

export default function QuizTake() {
  const location = useLocation();
  const navigate = useNavigate();
  const notify = useNotify();
  const { assessmentId: assessmentIdParam } = useParams();
  const assessmentId = assessmentIdParam != null ? Number(assessmentIdParam) : null;
  // Instant prefill (agent handoff / wizard) — the durable source is the
  // assessment itself, fetched below when an id is present.
  const [questions, setQuestions] = useState<Question[]>(
    () => (location.state?.questions as Question[]) ?? []
  );
  const [loading, setLoading] = useState(assessmentId != null && questions.length === 0);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [gradingProgress, setGradingProgress] = useState<{ done: number; total: number } | null>(null);

  // Deep-link path (/quiz/take/:assessmentId): load the session's questions
  // from the backend so refresh and agent navigation always resolve.
  useEffect(() => {
    if (assessmentId == null || questions.length > 0) return;
    let cancelled = false;
    getAssessment(assessmentId)
      .then((a) => {
        if (cancelled) return;
        setQuestions(a.questions ?? []);
        setLoading(false);
        if ((a.questions ?? []).length > 0 && a.status === "ready") {
          patchAssessment(assessmentId, "in_progress").catch(() => {});
        }
      })
      .catch((e) => {
        if (!cancelled) {
          notify.error((e as Error).message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [assessmentId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="max-w-md mx-auto text-center py-16 space-y-4 animate-fadeIn">
        <Loader2 size={24} className="mx-auto text-accent animate-spin" />
        <p className="text-xs text-muted-foreground">Loading your quiz…</p>
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="max-w-md mx-auto text-center py-16 space-y-4 animate-fadeIn">
        <div className="w-12 h-12 rounded-2xl bg-accent/10 text-accent border border-accent/20 flex items-center justify-center mx-auto">
          <Brain size={24} />
        </div>
        <h1 className="text-xl font-bold text-foreground">No Active Quiz Session</h1>
        <p className="text-xs text-muted-foreground max-w-xs mx-auto">
          No assessment questions found. Choose your topics and configure a new quiz to start.
        </p>
        <button className="btn text-xs py-2 px-4" onClick={() => navigate("/quiz")}>
          Go to Quiz Setup
        </button>
      </div>
    );
  }

  const q = questions[index];
  const isLast = index === questions.length - 1;
  const answeredCount = questions.filter((qq) => (answers[qq.id] ?? "").trim() !== "").length;

  async function submitAll() {
    setSubmitting(true);
    try {
      // Agent-created sessions reuse their assessment; the manual wizard flow
      // (no id) keeps the lazy-create behavior.
      const aid = assessmentId ?? (await createAssessment(USER_ID)).id;
      const results: GradedResult[] = [];
      let done = 0;
      for (const question of questions) {
        const answer = (answers[question.id] ?? "").trim();
        const attempt = await createAttempt({
          user_id: USER_ID,
          assessment_id: aid,
          question_id: question.id,
          user_answer: answer,
        });
        const graded = await gradeAttempt(attempt.id, { status: "answered" });
        done += 1;
        setGradingProgress({ done, total: questions.length });
        results.push({
          text: question.text,
          score: graded.score,
          feedback: graded.feedback ?? "",
          matched_key_points: graded.matched_key_points ?? [],
          missed_key_points: graded.missed_key_points ?? [],
        });
      }
      const total = results.reduce((s, r) => s + r.score, 0);
      if (assessmentId != null) {
        patchAssessment(assessmentId, "completed").catch(() => {});
      }
      navigate("/quiz/results", { state: { results, score: total / results.length } });
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setSubmitting(false);
      setGradingProgress(null);
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fadeIn">
      {/* Session Top Bar */}
      <div className="flex items-center justify-between pb-3 border-b border-border/60">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-accent/10 text-accent border border-accent/20 flex items-center justify-center">
            <Brain size={18} />
          </div>
          <div>
            <h1 className="text-base font-bold text-foreground">Active Assessment</h1>
            <span className="text-[11px] text-muted-foreground">
              Answer in your own words for deep semantic grading
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-xs font-mono font-bold text-foreground">
              Question {index + 1} of {questions.length}
            </div>
            <div className="text-[11px] text-accent font-medium">
              {answeredCount} of {questions.length} answered
            </div>
          </div>
        </div>
      </div>

      {/* Progress Bar with Gradient */}
      <div className="w-full bg-card rounded-full h-2 overflow-hidden border border-border">
        <div
          className="bg-gradient-to-r from-accent to-emerald-400 h-full rounded-full transition-all duration-300"
          style={{ width: `${(index + 1) / questions.length * 100}%` }}
        />
      </div>

      {/* Question quick selector pills */}
      <div className="flex gap-2 flex-wrap items-center">
        {questions.map((qq, i) => {
          const answered = (answers[qq.id] ?? "").trim() !== "";
          const active = i === index;
          return (
            <button
              key={qq.id}
              onClick={() => setIndex(i)}
              title={`Question ${i + 1}${answered ? " (answered)" : ""}`}
              className={`w-8 h-8 rounded-xl font-mono text-xs font-bold transition-all cursor-pointer flex items-center justify-center border ${
                active
                  ? "bg-primary text-primary-foreground border-accent shadow-sm scale-105"
                  : answered
                  ? "bg-green/15 text-green border-green/30"
                  : "bg-card/60 text-muted-foreground border-border hover:border-border"
              }`}
            >
              {i + 1}
            </button>
          );
        })}
      </div>

      {/* Question and Answer Card */}
      <div className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md backdrop-blur-sm space-y-4">
        <div className="flex items-start gap-3">
          <span className="px-2 py-0.5 rounded bg-accent/20 text-accent font-mono text-[11px] font-bold mt-0.5 flex-shrink-0">
            Q{index + 1}
          </span>
          <p className="text-base font-semibold text-foreground leading-relaxed">
            {q.text}
          </p>
        </div>

        <div className="pt-2">
          <textarea
            rows={6}
            placeholder="Type your explanation or response here in detail..."
            value={answers[q.id] ?? ""}
            onChange={(e) => setAnswers((p) => ({ ...p, [q.id]: e.target.value }))}
            className="w-full text-sm leading-relaxed p-4 rounded-xl resize-none"
            autoFocus
          />
          <div className="flex justify-between items-center text-[11px] text-muted-foreground mt-2 px-1">
            <span className="flex items-center gap-1">
              <Clock3 size={12} className="text-accent" /> Responses evaluated against curriculum rubrics
            </span>
            <span>
              {(answers[q.id] ?? "").split(/\s+/).filter(Boolean).length} words
            </span>
          </div>
        </div>
      </div>

      {/* Navigation Footer */}
      <div className="flex items-center justify-between pt-2">
        <button
          className="btn-secondary text-xs py-2.5 px-4"
          disabled={index === 0}
          onClick={() => setIndex((i) => i - 1)}
        >
          <ArrowLeft size={14} /> Previous
        </button>

        {isLast ? (
          <button
            className="btn text-xs py-2.5 px-6"
            disabled={submitting}
            onClick={submitAll}
          >
            {submitting ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                {gradingProgress
                  ? `Grading ${gradingProgress.done}/${gradingProgress.total} with AI...`
                  : "Evaluating Assessment..."}
              </>
            ) : (
              <>
                <Check size={14} /> Finish & Submit for Grading
              </>
            )}
          </button>
        ) : (
          <button
            className="btn text-xs py-2.5 px-5"
            onClick={() => setIndex((i) => i + 1)}
          >
            Next Question <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

