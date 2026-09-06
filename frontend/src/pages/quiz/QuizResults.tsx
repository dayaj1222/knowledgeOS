// Quiz results — score ring, per-question AI evaluation with matched/missed
// key points as chips, and a review flow.

import { useLocation, useNavigate } from "react-router-dom";
import {
  Check,
  X,
  RotateCcw,
  ChevronDown,
  Award,
} from "lucide-react";
import { useState } from "react";

interface Result {
  text: string;
  score: number;
  feedback: string;
  matched_key_points: string[];
  missed_key_points: string[];
}

export default function QuizResults() {
  const location = useLocation();
  const navigate = useNavigate();
  const results = (location.state?.results as Result[]) ?? [];
  const score = (location.state?.score as number) ?? 0;
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggle(i: number) {
    setExpanded((p) => {
      const n = new Set(p);
      n.has(i) ? n.delete(i) : n.add(i);
      return n;
    });
  }

  const pct = Math.round(score * 100);
  const isHigh = pct >= 80;
  const isMedium = pct >= 50;

  const colorClass = isHigh
    ? "text-emerald-400"
    : isMedium
    ? "text-accent"
    : "text-rose-400";

  const strokeColor = isHigh ? "#10b981" : isMedium ? "#6366f1" : "#f43f5e";

  const verdict = isHigh
    ? "Outstanding Performance!"
    : isMedium
    ? "Solid Progress — Review Misses"
    : "Needs Reinforcement — Re-study Recommended";

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-border/60">
        <div>
          <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-1">
            <Award size={14} /> Evaluation Complete
          </div>
          <h1 className="text-2xl font-extrabold text-foreground tracking-tight">
            Assessment Results
          </h1>
        </div>

        <button
          className="btn-secondary text-xs py-2 px-3 flex items-center gap-1.5"
          onClick={() => navigate("/quiz")}
        >
          <RotateCcw size={13} /> Try Another Quiz
        </button>
      </div>

      {/* Score Summary Card with Circular Radial Progress */}
      <div className="p-6 rounded-2xl bg-gradient-to-br from-card/90 via-card/60 to-muted/80 border border-border/80 shadow-md text-center relative overflow-hidden">
        <div className="relative z-10 max-w-sm mx-auto flex flex-col items-center">
          {/* Radial progress ring */}
          <div className="relative w-32 h-32 flex items-center justify-center mb-3">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="transparent"
                stroke="var(--border)"
                strokeWidth="8"
              />
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="transparent"
                stroke={strokeColor}
                strokeWidth="8"
                strokeDasharray={`${pct * 2.51} 251.2`}
                strokeLinecap="round"
                className="transition-all duration-1000 ease-out"
              />
            </svg>
            <div className="absolute flex flex-col items-center">
              <span className={`text-3xl font-extrabold tracking-tight ${colorClass}`}>
                {pct}%
              </span>
              <span className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">
                Mastery
              </span>
            </div>
          </div>

          <h2 className="text-lg font-bold text-foreground tracking-tight">{verdict}</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Proficiency vectors automatically adjusted across {results.length} tested topics.
          </p>
        </div>
      </div>

      {/* Per-Question Evaluation Breakdown */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Award size={14} className="text-accent" />
            Evaluation & Rubric Breakdown ({results.length} Questions)
          </span>
          <span className="text-[11px] text-muted-foreground">Click any card to expand key points</span>
        </div>

        {results.map((r, i) => {
          const open = expanded.has(i);
          const correct = r.score >= 0.6;
          const scorePercentage = Math.round(r.score * 100);
          const hasKeyPoints =
            (r.matched_key_points?.length ?? 0) > 0 || (r.missed_key_points?.length ?? 0) > 0;

          return (
            <div
              key={i}
              className="p-4 rounded-xl bg-card/60 border border-border/80 shadow-xs hover:border-border/80 transition-all text-xs"
            >
              <button
                onClick={() => toggle(i)}
                className="w-full flex items-start justify-between gap-3 text-left cursor-pointer group"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div
                    className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${
                      correct
                        ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
                        : "bg-rose-500/15 text-rose-400 border border-rose-500/20"
                    }`}
                  >
                    {correct ? <Check size={14} /> : <X size={14} />}
                  </div>
                  <div className="min-w-0">
                    <span className="text-[11px] font-mono font-bold text-muted-foreground block mb-0.5">
                      Question {i + 1}
                    </span>
                    <p className="font-semibold text-foreground group-hover:text-foreground leading-relaxed">
                      {r.text}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                  <span
                    className={`font-mono font-bold text-xs ${
                      correct ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {scorePercentage}%
                  </span>
                  <ChevronDown
                    size={14}
                    className={`text-muted-foreground transition-transform ${
                      open ? "rotate-180 text-accent" : ""
                    }`}
                  />
                </div>
              </button>

              {open && (
                <div className="mt-3.5 pt-3.5 border-t border-border/70 space-y-3 animate-fadeIn">
                  {hasKeyPoints ? (
                    <div className="space-y-2.5">
                      {(r.matched_key_points?.length ?? 0) > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
                            <Check size={12} /> Captured Key Points
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {r.matched_key_points.map((kp, j) => (
                              <span
                                key={j}
                                className="px-2.5 py-1 rounded-lg bg-emerald-950/40 text-emerald-300 border border-emerald-500/25 text-[11px]"
                              >
                                {kp}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {(r.missed_key_points?.length ?? 0) > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-[11px] font-bold text-rose-400 uppercase tracking-wider flex items-center gap-1">
                            <X size={12} /> Missed Critical Points
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {r.missed_key_points.map((kp, j) => (
                              <span
                                key={j}
                                className="px-2.5 py-1 rounded-lg bg-rose-950/40 text-rose-300 border border-rose-500/25 text-[11px]"
                              >
                                {kp}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-xs italic">
                      {r.feedback || "AI evaluation successfully logged to study history."}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Return Actions */}
      <div className="flex items-center justify-between pt-4 border-t border-border/60">
        <button
          className="btn-secondary text-xs py-2 px-4"
          onClick={() => navigate("/")}
        >
          Return to Dashboard
        </button>

        <button
          className="btn text-xs py-2 px-5"
          onClick={() => navigate("/quiz")}
        >
          <RotateCcw size={14} /> Start New Quiz Session
        </button>
      </div>
    </div>
  );
}

