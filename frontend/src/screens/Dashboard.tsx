import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  ArrowRight,
  CalendarClock,
  Timer,
  Brain,
  BookOpen,
  Target,
  TrendingUp,
  Award,
  Clock3,
  AlertTriangle,
  Play,
  CheckCircle2,
  Calendar,
} from "lucide-react";
import {
  getCourses,
  getProficiency,
  getDeadlines,
  getPlans,
  getModules,
  getTopics,
  USER_ID,
  type Topic,
} from "../api";
import { useFetch, Spinner } from "../hooks";
import { ProficiencyBar, EmptyState } from "../components/indicators";

interface TopicInfo {
  topicId: number;
  name: string;
  courseName: string;
}

function daysLeft(due: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(due);
  d.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86400000);
}

export default function Dashboard() {
  const courses = useFetch(() => getCourses(USER_ID));
  const proficiency = useFetch(() => getProficiency(USER_ID));
  const deadlines = useFetch(() => getDeadlines(USER_ID));
  const plans = useFetch(() => getPlans(USER_ID));

  const [topicInfo, setTopicInfo] = useState<TopicInfo[]>([]);

  useEffect(() => {
    const courseList = courses.data;
    if (!courseList) return;
    let cancelled = false;
    (async () => {
      const entries = await Promise.all(
        courseList.map(async (course) => {
          const modules = await getModules(course.id).catch(() => []);
          const topics = await Promise.all(
            modules.map((m) => getTopics(m.id).catch(() => [] as Topic[]))
          );
          return { courseName: course.name, topics: topics.flat() };
        })
      );
      if (!cancelled) {
        setTopicInfo(
          entries.flatMap(({ courseName, topics }) =>
            topics.map((t) => ({ topicId: t.id, name: t.name, courseName }))
          )
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [courses.data]);

  const topicNameById = useMemo(() => {
    const map = new Map<number, { name: string; courseName: string }>();
    for (const t of topicInfo) {
      map.set(t.topicId, { name: t.name, courseName: t.courseName });
    }
    return map;
  }, [topicInfo]);

  const weakTopics = useMemo(() => {
    const prof = proficiency.data ?? [];
    const sorted = [...prof].sort((a, b) => a.score - b.score);
    return sorted.slice(0, 4).map((p) => {
      const info = topicNameById.get(p.topic_id);
      return {
        topicId: p.topic_id,
        name: info?.name ?? `Topic #${p.topic_id}`,
        courseName: info?.courseName ?? "—",
        score: p.score,
      };
    });
  }, [proficiency.data, topicNameById]);

  const upcomingDeadlines = useMemo(() => {
    const list = deadlines.data ?? [];
    return [...list]
      .filter((d) => daysLeft(d.due_date) >= 0)
      .sort((a, b) => a.due_date.localeCompare(b.due_date));
  }, [deadlines.data]);

  const recentPlans = useMemo(() => {
    const list = plans.data ?? [];
    return [...list].sort((a, b) => b.generated_at.localeCompare(a.generated_at)).slice(0, 4);
  }, [plans.data]);

  // Overall statistics
  const averageProficiency = useMemo(() => {
    const prof = proficiency.data ?? [];
    if (prof.length === 0) return 0;
    const sum = prof.reduce((acc, curr) => acc + curr.score, 0);
    return Math.round((sum / prof.length) * 100);
  }, [proficiency.data]);

  const masteredTopicsCount = useMemo(() => {
    const prof = proficiency.data ?? [];
    return prof.filter((p) => p.score >= 0.75).length;
  }, [proficiency.data]);

  const anyLoading =
    courses.loading ||
    proficiency.loading ||
    deadlines.loading ||
    plans.loading;

  const anyError =
    courses.error ||
    proficiency.error ||
    deadlines.error ||
    plans.error;

  if (anyError) {
    return (
      <div className="p-6 rounded-2xl bg-rose-950/30 border border-rose-800/40 text-rose-200">
        <h1 className="text-xl font-bold flex items-center gap-2 mb-2">
          <AlertTriangle className="text-rose-400" size={20} /> Error loading dashboard
        </h1>
        <p className="text-sm opacity-90">
          {courses.error || proficiency.error || deadlines.error || plans.error}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header Banner with Greeting and Context */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-border/60">
        <div>
          <div className="flex items-center gap-2 text-accent text-xs font-semibold uppercase tracking-wider mb-1">
            Active Semester
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
            Study Overview
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Mastery tracking, targeted practice quizzes & upcoming deadlines
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link to="/quiz">
            <button className="btn group">
              <Brain size={16} className="group-hover:scale-110 transition-transform" />
              <span>Take Daily Quiz</span>
            </button>
          </Link>
          <Link to="/library">
            <button className="btn-secondary">
              <Plus size={15} />
              <span>Add Course</span>
            </button>
          </Link>
        </div>
      </div>

      {anyLoading && <Spinner />}

      {!anyLoading && (
        <>
          {/* Top KPI Metrics Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Metric 1: Total Courses */}
            <div className="p-5 rounded-2xl bg-gradient-to-br from-card/90 to-card/40 border border-border/80 shadow-md relative overflow-hidden group hover:border-accent/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Enrolled Courses
                </span>
                <div className="p-2.5 rounded-xl bg-accent/10 text-accent border border-accent/20">
                  <BookOpen size={18} />
                </div>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-foreground tracking-tight">
                  {courses.data?.length ?? 0}
                </span>
                <span className="text-xs text-muted-foreground">active courses</span>
              </div>
              <div className="mt-3 text-xs text-accent/80 flex items-center gap-1 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                {topicInfo.length} topics mapped in syllabus
              </div>
            </div>

            {/* Metric 2: Avg Mastery */}
            <div className="p-5 rounded-2xl bg-gradient-to-br from-card/90 to-card/40 border border-border/80 shadow-md relative overflow-hidden group hover:border-emerald-500/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Knowledge Mastery
                </span>
                <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <TrendingUp size={18} />
                </div>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-foreground tracking-tight">
                  {averageProficiency}%
                </span>
                <span className="text-xs text-emerald-400 font-medium">across subjects</span>
              </div>
              <div className="mt-3 text-xs text-muted-foreground flex items-center gap-1">
                <Award size={13} className="text-emerald-400" />
                {masteredTopicsCount} topics mastered (≥75%)
              </div>
            </div>

            {/* Metric 3: Target Deadlines */}
            <div className="p-5 rounded-2xl bg-gradient-to-br from-card/90 to-card/40 border border-border/80 shadow-md relative overflow-hidden group hover:border-amber-500/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Upcoming Deadlines
                </span>
                <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <CalendarClock size={18} />
                </div>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-foreground tracking-tight">
                  {upcomingDeadlines.length}
                </span>
                <span className="text-xs text-amber-400 font-medium">due soon</span>
              </div>
              <div className="mt-3 text-xs text-muted-foreground flex items-center gap-1">
                <Clock3 size={13} className="text-amber-400" />
                {upcomingDeadlines[0] ? `Next: ${upcomingDeadlines[0].title}` : "All tasks clear"}
              </div>
            </div>

            {/* Metric 4: Review Queue */}
            <div className="p-5 rounded-2xl bg-gradient-to-br from-card/90 to-card/40 border border-border/80 shadow-md relative overflow-hidden group hover:border-purple-500/30 transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Focus Areas
                </span>
                <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
                  <Target size={18} />
                </div>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-foreground tracking-tight">
                  {weakTopics.length}
                </span>
                <span className="text-xs text-purple-300 font-medium">needs review</span>
              </div>
              <div className="mt-3 text-xs text-muted-foreground flex items-center gap-1">
                <Clock3 size={13} className="text-purple-400" />
                Scheduled for revision
              </div>
            </div>
          </div>

          {/* Main Grid: Priority Study Focus + Deadlines */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left 2 Cols: Priority Topics Needing Study */}
            <div className="lg:col-span-2 space-y-6">
              <section className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md relative backdrop-blur-sm">
                <div className="flex items-center justify-between mb-5">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-accent/10 text-accent">
                      <Target size={18} />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground leading-tight">
                        Priority Focus Areas
                      </h2>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Topics with lower proficiency scores recommended for immediate review
                      </p>
                    </div>
                  </div>
                  <Link to="/quiz">
                    <button className="text-xs font-semibold text-accent hover:text-accent flex items-center gap-1 transition-colors">
                      Custom Quiz <ArrowRight size={13} />
                    </button>
                  </Link>
                </div>

                {weakTopics.length === 0 ? (
                  <EmptyState
                    message="No study data yet — add courses and take your first assessment."
                    action={
                      <Link to="/library">
                        <button className="btn mt-2">
                          <Plus size={14} /> Add First Course
                        </button>
                      </Link>
                    }
                  />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                    {weakTopics.map((t) => {
                      const pct = Math.round(t.score * 100);
                      const isCritical = pct < 40;
                      return (
                        <div
                          key={t.topicId}
                          className="p-4 rounded-xl bg-muted/60 border border-border/70 hover:border-accent/30 transition-all flex flex-col justify-between group relative overflow-hidden"
                        >
                          <div className="absolute top-0 right-0 w-24 h-24 bg-accent/5 rounded-full blur-xl pointer-events-none group-hover:bg-accent/10 transition-all" />
                          
                          <div>
                            <div className="flex items-center justify-between gap-2 mb-1.5">
                              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider truncate max-w-[150px]">
                                {t.courseName}
                              </span>
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                  isCritical
                                    ? "bg-rose-500/15 text-rose-400 border border-rose-500/25"
                                    : "bg-amber-500/15 text-amber-400 border border-amber-500/25"
                                }`}
                              >
                                {isCritical ? "Needs Review" : "In Progress"}
                              </span>
                            </div>

                            <h3 className="text-sm font-bold text-foreground line-clamp-1 group-hover:text-accent transition-colors">
                              {t.name}
                            </h3>

                            <div className="mt-3 space-y-1.5">
                              <div className="flex justify-between text-xs font-mono">
                                <span className="text-muted-foreground">Proficiency</span>
                                <span className={isCritical ? "text-rose-400" : "text-amber-400"}>
                                  {pct}%
                                </span>
                              </div>
                              <ProficiencyBar score={t.score} />
                            </div>
                          </div>

                          <div className="mt-4 pt-3 border-t border-border/60 flex items-center justify-between">
                            <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                              <Clock3 size={12} /> ~15 min quiz
                            </span>
                            <Link to="/quiz">
                              <button className="px-3 py-1.5 rounded-lg bg-primary/20 hover:bg-primary text-accent hover:text-primary-foreground text-xs font-semibold transition-all flex items-center gap-1.5 border border-accent/30">
                                <Play size={12} className="fill-current" />
                                Practice
                              </button>
                            </Link>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              {/* Recently Studied History */}
              <section className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md backdrop-blur-sm">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
                      <CheckCircle2 size={18} />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground leading-tight">
                        Recently Completed Sessions
                      </h2>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Historical study blocks and completed revision plans
                      </p>
                    </div>
                  </div>
                  <Link to="/plan">
                    <button className="text-xs font-semibold text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors">
                      Full Schedule <ArrowRight size={13} />
                    </button>
                  </Link>
                </div>

                {recentPlans.length === 0 ? (
                  <EmptyState message="No recorded study sessions yet." />
                ) : (
                  <div className="space-y-2.5">
                    {recentPlans.map((p) => {
                      const info = topicNameById.get(p.topic_id);
                      const name = info?.name ?? `Topic #${p.topic_id}`;
                      const courseName = info?.courseName ?? "—";
                      return (
                        <div
                          key={p.id}
                          className="flex items-center justify-between p-3.5 rounded-xl bg-muted/40 border border-border/60 hover:bg-card/60 transition-colors"
                        >
                          <div className="flex items-center gap-3.5 min-w-0">
                            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 flex-shrink-0">
                              <CheckCircle2 size={15} />
                            </div>
                            <div className="min-w-0">
                              <div className="font-semibold text-sm text-foreground truncate">
                                {name}
                              </div>
                              <div className="text-xs text-muted-foreground truncate">
                                {courseName}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2.5 flex-shrink-0 ml-4">
                            <span className="chip">
                              <Timer size={12} className="mr-1 text-muted-foreground" />
                              {p.suggested_duration_minutes}m
                            </span>
                            <span className="chip success">
                              {p.status || "completed"}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            </div>

            {/* Right Column: Deadlines & Calendar Quickview */}
            <div className="space-y-6">
              <section className="p-6 rounded-2xl bg-card/60 border border-border/80 shadow-md backdrop-blur-sm">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400">
                      <CalendarClock size={18} />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-foreground leading-tight">
                        Upcoming Milestones
                      </h2>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Exam & assignment targets
                      </p>
                    </div>
                  </div>
                  <Link to="/plan">
                    <button className="p-1 rounded text-muted-foreground hover:text-foreground" title="Add deadline">
                      <Plus size={16} />
                    </button>
                  </Link>
                </div>

                {upcomingDeadlines.length === 0 ? (
                  <EmptyState message="No scheduled deadlines." />
                ) : (
                  <div className="space-y-3">
                    {upcomingDeadlines.map((d) => {
                      const dl = daysLeft(d.due_date);
                      const isUrgent = dl <= 2;
                      return (
                        <div
                          key={d.id}
                          className={`p-3.5 rounded-xl border transition-all ${
                            isUrgent
                              ? "bg-rose-950/20 border-rose-800/40 hover:border-rose-700/60"
                              : "bg-muted/40 border-border/60 hover:border-border/60"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="font-semibold text-sm text-foreground">
                              {d.title}
                            </div>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full flex-shrink-0 ${
                                isUrgent
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : "bg-muted text-foreground border border-border"
                              }`}
                            >
                              {dl === 0
                                ? "Due Today"
                                : dl === 1
                                ? "Tomorrow"
                                : `${dl} days left`}
                            </span>
                          </div>

                          <div className="mt-2.5 flex items-center justify-between text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Calendar size={12} className="text-muted-foreground" />
                              {d.due_date}
                            </span>
                            {d.weight > 0 && (
                              <span className="font-mono text-[11px] text-amber-400/90 font-medium">
                                Weight: {d.weight}%
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              {/* Study Tip & Strategy Box */}
              <div className="p-5 rounded-2xl bg-card/60 border border-border/80 shadow-md">
                <div className="flex items-center gap-2 text-accent font-semibold text-xs mb-2">
                  <Target size={14} /> Spaced Repetition Principle
                </div>
                <p className="text-xs text-foreground leading-relaxed">
                  Reviewing low-proficiency topics within 24 hours of quiz completion significantly boosts long-term retention. Generate a quick practice set to solidify recall.
                </p>
                <div className="mt-3.5 pt-3 border-t border-accent/10 flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground">Recommended today</span>
                  <Link to="/quiz">
                    <span className="text-xs text-accent font-semibold hover:underline flex items-center gap-1 cursor-pointer">
                      Start session <ArrowRight size={11} />
                    </span>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
