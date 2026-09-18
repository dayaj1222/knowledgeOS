// Tutor — the primary learning place. Full-page chat: history rail with
// search/rename/delete, markdown thread with tool transparency, suggestion
// prompts, and a preferences modal (system-prompt injection + tutor memory).

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowDown,
  Check,
  Copy,
  History,
  Pin,
  PinOff,
  Plus,
  Reply,
  Search,
  Settings2,
  Sparkles,
  Square,
  Timer,
  Trash2,
  X,
} from "lucide-react";
import {
  USER_ID,
  deleteConversation,
  deleteMemory,
  getDeadlines,
  getDueReviews,
  getMemories,
  getPreference,
  pinConversation,
  putPreference,
  type TutorMemory,
} from "../api";
import { useStore } from "../store";
import { notifyError, notifySuccess } from "../components/notifications";
import { useChatThread, dropThreadCache } from "../components/useChatThread";
import Markdown from "../components/Markdown";
import TodoGraph from "../components/TodoGraph";
import { renderCard } from "../components/cardRegistry";
import { cardKind } from "../api";
import ToolCalls, { ToolActivity } from "../components/ToolCalls";
import ChatComposer from "../components/ChatComposer";
import { ModulePickList, SUGGESTIONS, UserText } from "../components/tutorPieces";

export default function Tutor() {
  const navigate = useNavigate();
  const {
    activeConversationId,
    setActiveConversationId,
    proficiency,
    topicsByModule,
    courses,
    allCourseTrees,
  } = useStore();
  const {
    conversations,
    refreshList,
    messages,
    busy,
    streamText,
    liveTools,
    send: sendStream,
    submitQuiz,
    retry,
    timer,
    stopTimer,
    todo,
    activePin,
    startPinned,
  } = useChatThread();
  const [pinMenuOpen, setPinMenuOpen] = useState(false);
  const [newMenuOpen, setNewMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [memories, setMemories] = useState<TutorMemory[]>([]);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [historyPopupOpen, setHistoryPopupOpen] = useState(false);
  // Quote-reply: the message being answered (quote bar above the composer).
  const [replyTo, setReplyTo] = useState<{ id: number; role: string; text: string } | null>(null);
  // Selection-reply: floating pill for a text snippet selected in the thread.
  const [selMenu, setSelMenu] = useState<{ x: number; y: number; text: string; id: number; role: string } | null>(null);
  // Quick stats bar: what's due / upcoming, tappable into agent actions.
  const [dueCount, setDueCount] = useState(0);
  const [deadlineCount, setDeadlineCount] = useState(0);
  // Timer pill clock.
  const [now, setNow] = useState(() => Date.now());
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Stick-to-bottom: follow only while pinned to the absolute bottom.
  // Any scroll-up unpins, so streaming never yanks away reading.
  const stickRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  const activeTitle = conversations.find((c) => c.id === activeConversationId)?.title;

  // Dynamic suggestion: weakest scored topic.
  const weakestName = useMemo(() => {
    if (proficiency.length === 0) return null;
    const nameById: Record<number, string> = {};
    for (const list of Object.values(topicsByModule)) for (const t of list) nameById[t.id] = t.name;
    const worst = [...proficiency].sort((a, b) => a.score - b.score)[0];
    return nameById[worst.topic_id] ?? null;
  }, [proficiency, topicsByModule]);

  const suggestions = weakestName
    ? [`Quiz me on ${weakestName}`, ...SUGGESTIONS.slice(1)]
    : SUGGESTIONS;

  const filtered = query.trim()
    ? conversations.filter((c) => c.title.toLowerCase().includes(query.trim().toLowerCase()))
    : conversations;

  useEffect(() => {
    // Follow only while pinned to the absolute bottom. Direct scrollTop
    // (not smooth scrollIntoView) so per-token streaming can't queue up
    // animations that drag the view after the user scrolled away.
    if (!stickRef.current) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    else bottomRef.current?.scrollIntoView({ behavior: "auto" });
  }, [messages, busy, streamText]);

  // New conversation → start pinned to the bottom again.
  useEffect(() => {
    stickRef.current = true;
    setAtBottom(true);
    setReplyTo(null);
    setSelMenu(null);
  }, [activeConversationId]);

  // Quick stats: refresh on mount and after every completed turn (reviews
  // and deadlines shift as the learner works).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [due, deadlines] = await Promise.all([
          getDueReviews(USER_ID, 20).catch(() => []),
          getDeadlines(USER_ID).catch(() => []),
        ]);
        if (!cancelled) {
          setDueCount(due.length);
          setDeadlineCount(deadlines.length);
        }
      } catch {
        // best-effort; the bar just stays at zero
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [busy]);

  // Timer pill clock (1s tick, only while a timer runs).
  useEffect(() => {
    if (!timer) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [timer]);

  // Keyboard shortcuts: "/" focuses the composer, Escape blurs it.
  // Clicking anywhere outside the selection pill dismisses it.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = document.activeElement as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA");
      if (e.key === "/" && !typing) {
        e.preventDefault();
        document.getElementById("tutor-composer")?.focus();
      } else if (e.key === "Escape") {
        setSelMenu(null);
        if (typing) el?.blur();
      }
    }
    function onDown(e: MouseEvent) {
      if (!(e.target as HTMLElement).closest?.(".sel-pill")) setSelMenu(null);
    }
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, []);

  function onThreadSelect() {
    // Read the selection after it settles; show a Reply pill attributed to
    // the message the selection started in.
    requestAnimationFrame(() => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) {
        setSelMenu(null);
        return;
      }
      const text = sel.toString().trim();
      if (!text) {
        setSelMenu(null);
        return;
      }
      const node = sel.anchorNode as Node | null;
      const host = (node instanceof Element ? node : node?.parentElement)?.closest?.("[data-msg-id]");
      if (!host) {
        setSelMenu(null);
        return;
      }
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      if (rect.width < 2 && rect.height < 2) {
        setSelMenu(null);
        return;
      }
      setSelMenu({
        x: Math.min(Math.max(rect.left + rect.width / 2, 60), window.innerWidth - 60),
        y: Math.max(rect.top - 8, 8),
        text: text.slice(0, 600),
        id: Number(host.getAttribute("data-msg-id")),
        role: host.getAttribute("data-msg-role") || "assistant",
      });
    });
  }

  function onScroll(e: React.UIEvent<HTMLDivElement>) {
    // Absolute bottom: pinned only when truly at the end (≤4px slack).
    const el = e.currentTarget;
    const pinned = el.scrollHeight - el.scrollTop - el.clientHeight <= 4;
    stickRef.current = pinned;
    setAtBottom((prev) => (prev === pinned ? prev : pinned));
    setSelMenu(null); // scrolling dismisses the selection pill
  }

  function jumpToLatest() {
    stickRef.current = true;
    setAtBottom(true);
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    else bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  function startReply(id: number, role: string, content: string) {
    const text = content.trim().slice(0, 600);
    if (!text) return;
    setReplyTo({ id, role, text });
    document.getElementById("tutor-composer")?.focus();
  }

  function quotedSend(text: string) {
    // Quote-reply composes a markdown blockquote above the message, so the
    // tutor sees exactly which section is being answered (frontend-only).
    if (!replyTo) return text;
    const quote = replyTo.text
      .split("\n")
      .map((l) => `> ${l}`)
      .join("\n");
    return `${quote}\n\n${text}`;
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    stickRef.current = true; // own message → follow the reply
    setAtBottom(true);
    setSelMenu(null);
    const body = quotedSend(text);
    setReplyTo(null);
    const cmd = text.trim().toLowerCase();
    if (cmd === "/history") {
      setHistoryPopupOpen(true);
      return;
    }
    if (cmd === "/new") {
      startPinned(null);
      notifySuccess("Started a new chat.");
      return;
    }
    if (cmd === "/quiz") {
      await sendStream("Generate a practice quiz for me");
      return;
    }
    if (cmd === "/review") {
      await sendStream("What do I have due for review? Let's revise.");
      return;
    }
    if (cmd === "/plan") {
      await sendStream("Build a study plan for me");
      return;
    }
    await sendStream(body);
  }

  async function remove(id: number) {
    try {
      await deleteConversation(id);
      dropThreadCache(id);
      if (activeConversationId === id) setActiveConversationId(null);
      refreshList();
    } catch (e) {
      notifyError((e as Error).message);
    }
  }

  async function openPrefs() {
    setPrefsOpen(true);
    try {
      const [pref, mems] = await Promise.all([
        getPreference(USER_ID).catch(() => null),
        getMemories().catch(() => [] as TutorMemory[]),
      ]);
      setInstructions(pref?.tutor_instructions ?? "");
      setMemories(mems);
    } catch (e) {
      notifyError((e as Error).message);
    }
  }

  async function saveInstructions() {
    try {
      await putPreference({ tutor_instructions: instructions });
      notifySuccess("Tutor instructions saved — they apply from the next message.");
      setPrefsOpen(false);
    } catch (e) {
      notifyError((e as Error).message);
    }
  }

  async function removeMemory(id: number) {
    try {
      await deleteMemory(id);
      setMemories((m) => m.filter((x) => x.id !== id));
    } catch (e) {
      notifyError((e as Error).message);
    }
  }

  function copy(text: string, id: number) {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1500);
    });
  }

  // Re-pin the active thread (PATCH, no chat noise) or set the pending pin
  // for a brand-new conversation.
  async function repin(mod: { id: number; name: string } | null) {
    setPinMenuOpen(false);
    setNewMenuOpen(false);
    if (activeConversationId == null) {
      startPinned(mod);
      return;
    }
    try {
      await pinConversation(activeConversationId, mod?.id ?? null);
      await refreshList();
      notifySuccess(mod ? `Pinned to ${mod.name}.` : "Unpinned.");
    } catch (e) {
      notifyError((e as Error).message);
    }
  }

  return (
    <div className="flex gap-4 items-start animate-fadeIn h-[calc(100vh-3.5rem)]">
      {/* Main thread */}
      <div className="flex-1 rounded-xl bg-card border border-border flex flex-col h-full overflow-hidden min-w-0 relative">
        <div className="flex items-center gap-2 px-5 py-3.5 border-b border-border">
          <Sparkles size={16} className="text-accent shrink-0" />
          <h1 className="text-sm font-semibold text-foreground truncate">
            {activeTitle ?? "New conversation"}
          </h1>
          {/* Module pin chip: stored pin on threads, pending pin on new chats */}
          <div className="relative shrink-0">
            <button
              onClick={() => setPinMenuOpen((o) => !o)}
              title={activePin ? `Pinned to ${activePin.name}` : "Unpinned chat"}
              className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border font-semibold max-w-48 ${
                activePin
                  ? "bg-accent/10 text-accent border-accent/30"
                  : "bg-muted/50 text-muted-foreground border-border/70"
              }`}
            >
              {activePin ? <Pin size={12} /> : <PinOff size={12} />}
              <span className="truncate">{activePin?.name ?? "Unpinned"}</span>
            </button>
            {pinMenuOpen && (
              <div className="absolute z-30 mt-1.5 left-0 w-64 rounded-xl bg-card border border-border shadow-lg p-1.5 space-y-0.5 max-h-72 overflow-y-auto">
                <ModulePickList courses={courses} allCourseTrees={allCourseTrees} onPick={repin} />
              </div>
            )}
          </div>
          {timer && (
            <div
              title={timer.label}
              className="flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-1.5 rounded-lg bg-accent/10 text-accent border border-accent/30 shrink-0"
            >
              <Timer size={13} />
              <span>
                {String(Math.floor((now - timer.startedAt) / 60000)).padStart(2, "0")}:
                {String(Math.floor(((now - timer.startedAt) / 1000) % 60)).padStart(2, "0")}
              </span>
              <span className="font-sans font-medium max-w-32 truncate hidden sm:inline">
                {timer.label}
              </span>
              <button
                onClick={stopTimer}
                title="Stop timer and log the session"
                className="p-0.5 rounded hover:bg-accent/20"
              >
                <Square size={11} />
              </button>
            </div>
          )}
          <div className="ml-auto flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => setHistoryPopupOpen(true)}
              title="Chat history"
              className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted"
            >
              <History size={14} />
            </button>
            <button
              onClick={openPrefs}
              title="Tutor preferences"
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground px-2.5 py-1.5 rounded-lg hover:bg-muted"
            >
              <Settings2 size={13} /> Customize
            </button>
          </div>
        </div>

        {(dueCount > 0 || deadlineCount > 0) && (
          <div className="flex items-center gap-2 px-5 py-2 border-b border-border/60 text-xs">
            {dueCount > 0 && (
              <button
                onClick={() => send("What do I have due for review? Let's revise.")}
                disabled={busy}
                className="font-semibold text-accent hover:underline disabled:opacity-50"
              >
                {dueCount} review{dueCount === 1 ? "" : "s"} due
              </button>
            )}
            {dueCount > 0 && deadlineCount > 0 && (
              <span className="text-muted-foreground/50">·</span>
            )}
            {deadlineCount > 0 && (
              <button
                onClick={() => navigate("/plan")}
                className="text-muted-foreground hover:text-foreground hover:underline"
              >
                {deadlineCount} upcoming deadline{deadlineCount === 1 ? "" : "s"}
              </button>
            )}
          </div>
        )}

        <div className="relative flex-1 overflow-hidden">
          <div className="pointer-events-none absolute top-0 inset-x-0 h-6 bg-gradient-to-b from-card to-transparent z-10" />
          <div ref={scrollRef} onScroll={onScroll} onMouseUp={onThreadSelect} onTouchEnd={onThreadSelect} className="flex-1 overflow-y-auto px-5 py-4 space-y-6 w-full mx-auto h-full">
          {messages.filter((m) => m.role !== "todo").length === 0 && (
            <div className="py-10 text-center space-y-5">
              <div>
                <Sparkles size={28} className="mx-auto text-accent mb-3" />
                <h2 className="text-lg font-bold text-foreground">What are we learning today?</h2>
                <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
                  I can see your courses, quiz you, build plans, and control the app — just ask.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    disabled={busy}
                    className="text-xs px-3 py-2 rounded-full bg-muted/70 border border-border text-foreground hover:border-accent/50 hover:bg-accent/10 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.filter((m) => m.role !== "todo" && cardKind(m) !== "todo").map((m) => {
            const card = cardKind(m) && cardKind(m) !== "todo"
              ? renderCard(m, {
                  conversationId: activeConversationId ?? 0,
                  busy,
                  onQuizFinish: submitQuiz,
                  onClarifyAnswer: (a) => send(a),
                })
              : null;
            if (card) return card;
            return (
            <div key={m.id} data-msg-id={m.id} data-msg-role={m.role} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`group/msg max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                  m.role === "user"
                    ? "bg-primary text-white rounded-br-sm"
                    : "bg-muted border border-border rounded-bl-sm"
                }`}
              >
                {m.role === "user" ? (
                  <>
                    {m.content && <UserText text={m.content} />}
                    {m.images?.map((image, index) => (
                      <figure key={`${m.id}-${index}`} className={m.content ? "mt-3" : ""}>
                        <img
                          src={image}
                          alt={`Attached image ${index + 1}`}
                          className="block max-h-96 max-w-full rounded-xl border border-white/30 bg-black/10 object-contain shadow-sm"
                        />
                        <figcaption className="mt-1 text-[10px] font-medium text-white/75">
                          Attached image
                        </figcaption>
                      </figure>
                    ))}
                  </>
                ) : (
                  <Markdown text={m.content} />
                )}
                {m.role === "assistant" && m.content.startsWith("Something went wrong") && (
                  <button
                    onClick={retry}
                    disabled={busy}
                    className="mt-2 text-xs font-semibold px-3 py-1.5 rounded-lg bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25 disabled:opacity-50"
                  >
                    Retry
                  </button>
                )}
                <ToolCalls calls={m.tool_calls ?? []} />
                <div className="flex items-center gap-2 mt-2 pt-1.5 border-t border-border/40">
                  {m.created_at && (
                    <span className="text-[10px] font-mono text-muted-foreground/70">
                      {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-1">
                    {m.content.trim() && (
                      <button
                        title="Reply to this message"
                        onClick={() => startReply(m.id, m.role, m.content)}
                        className="opacity-0 group-hover/msg:opacity-60 hover:!opacity-100 p-0.5"
                      >
                        <Reply size={11} />
                      </button>
                    )}
                    {m.role === "assistant" && m.id > 0 && (
                      <button
                        title="Copy"
                        onClick={() => copy(m.content, m.id)}
                        className="opacity-0 group-hover/msg:opacity-60 hover:!opacity-100 p-0.5"
                      >
                        {copiedId === m.id ? <Check size={11} /> : <Copy size={11} />}
                      </button>
                    )}
                  </span>
                </div>
              </div>
            </div>
            );
          })}
          {busy && streamText && (
            <div className="flex justify-start">
              <div className="max-w-[75%] rounded-2xl rounded-bl-sm px-4 py-3 text-sm leading-relaxed bg-muted text-foreground border border-border shadow-sm">
                <Markdown text={streamText} />
                <ToolCalls calls={liveTools} />
                <span className="inline-block w-2 h-4 ml-1 -mb-0.5 bg-accent/70 animate-pulse" />
              </div>
            </div>
          )}
          {busy && !streamText && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-md px-3 py-2.5 bg-muted/60 border border-border/60 text-sm text-muted-foreground min-w-40">
                {liveTools.length > 0 ? (
                  <ToolActivity names={[...new Set(liveTools.map((t) => t.tool))]} />
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="flex gap-1" aria-hidden="true">
                      <span className="h-1.5 w-1.5 rounded-full bg-accent/70 animate-pulse" />
                      <span className="h-1.5 w-1.5 rounded-full bg-accent/50 animate-pulse [animation-delay:150ms]" />
                      <span className="h-1.5 w-1.5 rounded-full bg-accent/30 animate-pulse [animation-delay:300ms]" />
                    </span>
                    Thinking…
                  </div>
                )}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
          </div>
        </div>

        {!atBottom && (
          <button
            onClick={jumpToLatest}
            className="absolute bottom-24 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 text-xs font-semibold px-3.5 py-2 rounded-full bg-primary text-white shadow-lg hover:opacity-90 transition-opacity"
          >
            <ArrowDown size={13} /> Latest
          </button>
        )}

        {/* Selection-reply pill: answer just the highlighted snippet. */}
        {selMenu && (
          <button
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              startReply(selMenu.id, selMenu.role, selMenu.text);
              setSelMenu(null);
              window.getSelection()?.removeAllRanges();
            }}
            className="sel-pill fixed z-40 flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full bg-primary text-white shadow-lg hover:opacity-90 transition-opacity animate-fadeIn"
            style={{ left: selMenu.x, top: selMenu.y, transform: "translate(-50%, -100%)" }}
          >
            <Reply size={12} /> Reply
          </button>
        )}

        {replyTo && (
          <div className="mx-5 mb-2.5 flex items-start gap-2.5 rounded-xl bg-muted/60 border border-border/70 border-l-2 border-l-accent px-3 py-2 animate-fadeIn">
            <Reply size={13} className="text-accent shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-accent">
                Replying to {replyTo.role === "user" ? "you" : "tutor"}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {replyTo.text.split("\n")[0].slice(0, 140)}
                {(replyTo.text.length > 140 || replyTo.text.includes("\n")) ? "…" : ""}
              </p>
            </div>
            <button
              onClick={() => setReplyTo(null)}
              title="Cancel reply"
              className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted shrink-0"
            >
              <X size={13} />
            </button>
          </div>
        )}
        <ChatComposer busy={busy} onSend={send} />
      </div>

      {/* Plan side panel: appears only while the active conversation has a
          live todo plan (agent update_todo). Per-chat: switching threads
          swaps to that thread's plan, or hides when it has none. */}
      {todo && todo.todos.length > 0 && (
        <aside className="shrink-0 w-64 max-h-[calc(100vh-3.5rem)] overflow-y-auto max-lg:fixed max-lg:right-3 max-lg:top-14 max-lg:bottom-16 max-lg:z-30 max-lg:w-72 max-lg:rounded-xl max-lg:border max-lg:border-border max-lg:bg-card max-lg:p-3 max-lg:shadow-xl">
          <TodoGraph todo={todo} />
        </aside>
      )}

      {/* History popup */}
      {historyPopupOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setHistoryPopupOpen(false)}>
          <div
            className="w-full max-w-md rounded-2xl bg-card border border-border p-5 space-y-3 max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-foreground">Chat history</h2>
              <button onClick={() => setHistoryPopupOpen(false)} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted">
                <X size={15} />
              </button>
            </div>

            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search chats…"
                className="text-xs pl-8 w-full rounded-lg bg-muted/50 border border-border/70 py-2 pr-2 text-foreground placeholder:text-muted-foreground/60 focus:border-accent/60 focus:bg-card transition-colors"
              />
            </div>

            <div className="space-y-1">
              {filtered.map((c) => (
                <div
                  key={c.id}
                  onClick={() => {
                    setActiveConversationId(c.id);
                    setHistoryPopupOpen(false);
                  }}
                  className={`group rounded-lg px-3 py-2 text-xs cursor-pointer border transition-colors ${
                    c.id === activeConversationId
                      ? "bg-accent/10 border-accent/30 text-foreground font-medium"
                      : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/60"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="flex-1 truncate">{c.title}</span>
                    {c.module_name && (
                      <span
                        title={`Pinned to ${c.module_name}`}
                        className="shrink-0 text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-accent/15 text-accent border border-accent/30 truncate max-w-28"
                      >
                        {c.module_name}
                      </span>
                    )}
                    <button
                      title="Delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        remove(c.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-muted text-muted-foreground hover:text-rose-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
              {filtered.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-6">
                  {query ? "No matches." : "No chats yet."}
                </p>
              )}
            </div>

            <div className="relative">
              <button
                onClick={() => setNewMenuOpen((o) => !o)}
                className="btn text-xs py-2 w-full"
              >
                <Plus size={13} /> New chat
              </button>
              {newMenuOpen && (
                <div className="absolute z-30 mb-1.5 bottom-full left-0 w-full rounded-xl bg-card border border-border shadow-lg p-1.5 space-y-0.5 max-h-72 overflow-y-auto">
                  <ModulePickList courses={courses} allCourseTrees={allCourseTrees} onPick={repin} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Preferences modal */}
      {prefsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setPrefsOpen(false)}>
          <div
            className="w-full max-w-lg rounded-2xl bg-card border border-border p-5 space-y-4 max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-foreground">Tutor preferences</h2>
              <button onClick={() => setPrefsOpen(false)} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted">
                <X size={15} />
              </button>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground">
                Custom instructions <span className="font-normal text-muted-foreground">— injected into my system prompt every turn</span>
              </label>
              <textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                rows={5}
                placeholder={"e.g. Quiz me with hard questions only.\nExplain like I'm revising the night before the exam.\nAlways give a worked example after theory."}
                className="text-xs w-full"
              />
              <button onClick={saveInstructions} className="btn text-xs py-2 px-4">
                <Check size={13} /> Save instructions
              </button>
            </div>

            <div className="space-y-2 pt-1 border-t border-border">
              <h3 className="text-xs font-semibold text-foreground pt-3">
                What I remember about you <span className="font-normal text-muted-foreground">({memories.length})</span>
              </h3>
              {memories.length === 0 && (
                <p className="text-xs text-muted-foreground">Nothing stored yet — I'll save lasting notes here as we talk.</p>
              )}
              {memories.map((mem) => (
                <div key={mem.id} className="flex items-start gap-2 rounded-lg bg-muted/50 border border-border/60 px-2.5 py-2 text-xs">
                  <div className="flex-1 min-w-0">
                    <span className="font-semibold text-foreground">{mem.key}: </span>
                    <span className="text-muted-foreground">{mem.value}</span>
                  </div>
                  <button
                    title="Forget"
                    onClick={() => removeMemory(mem.id)}
                    className="p-1 rounded text-muted-foreground hover:text-rose-400 shrink-0"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
