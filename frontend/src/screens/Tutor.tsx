// Tutor — the primary learning place. Full-page chat: history rail with
// search/rename/delete, markdown thread with tool transparency, suggestion
// prompts, and a preferences modal (system-prompt injection + tutor memory).

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  Check,
  Copy,
  Plus,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  USER_ID,
  deleteConversation,
  deleteMemory,
  getMemories,
  getPreference,
  putPreference,
  type TutorMemory,
} from "../api";
import { useStore } from "../store";
import { notifyError, notifySuccess } from "../components/notifications";
import { useChatThread, dropThreadCache } from "../components/useChatThread";
import Markdown from "../components/Markdown";
import InlineQuiz from "../components/InlineQuiz";
import InlineClarify from "../components/InlineClarify";
import ToolCalls from "../components/ToolCalls";
import ChatComposer from "../components/ChatComposer";

const SUGGESTIONS = [
  "Quiz me on my weakest topic",
  "What should I study today?",
  "Explain the last thing I got wrong",
  "Plan my study week",
];

export default function Tutor() {
  const {
    activeConversationId,
    setActiveConversationId,
    proficiency,
    topicsByModule,
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
  } = useChatThread();

  const [query, setQuery] = useState("");
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [memories, setMemories] = useState<TutorMemory[]>([]);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [historyPopupOpen, setHistoryPopupOpen] = useState(false);
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
  }, [activeConversationId]);

  function onScroll(e: React.UIEvent<HTMLDivElement>) {
    // Absolute bottom: pinned only when truly at the end (≤4px slack).
    const el = e.currentTarget;
    const pinned = el.scrollHeight - el.scrollTop - el.clientHeight <= 4;
    stickRef.current = pinned;
    setAtBottom((prev) => (prev === pinned ? prev : pinned));
  }

  function jumpToLatest() {
    stickRef.current = true;
    setAtBottom(true);
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    else bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    stickRef.current = true; // own message → follow the reply
    setAtBottom(true);
    const cmd = text.trim().toLowerCase();
    if (cmd === "/history") {
      setHistoryPopupOpen(true);
      return;
    }
    if (cmd === "/new") {
      setActiveConversationId(null);
      notifySuccess("Started a new chat.");
      return;
    }
    if (cmd === "/quiz") {
      await sendStream("Generate a practice quiz for me");
      return;
    }
    if (cmd === "/plan") {
      await sendStream("Build a study plan for me");
      return;
    }
    await sendStream(text);
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

  return (
    <div className="flex gap-4 items-start animate-fadeIn h-[calc(100vh-3.5rem)]">
      {/* Main thread */}
      <div className="flex-1 rounded-xl bg-card border border-border flex flex-col h-full overflow-hidden min-w-0 relative">
        <div className="flex items-center gap-2 px-5 py-3.5 border-b border-border">
          <Sparkles size={16} className="text-accent shrink-0" />
          <h1 className="text-sm font-semibold text-foreground truncate">
            {activeTitle ?? "New conversation"}
          </h1>
          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={openPrefs}
              title="Tutor preferences"
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground px-2.5 py-1.5 rounded-lg hover:bg-muted"
            >
              <Settings2 size={13} /> Customize
            </button>
          </div>
        </div>

        <div className="relative flex-1 overflow-hidden">
          <div className="pointer-events-none absolute top-0 inset-x-0 h-6 bg-gradient-to-b from-card to-transparent z-10" />
          <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-5 py-4 space-y-6 w-full mx-auto h-full">
          {messages.length === 0 && (
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

          {messages.map((m) => (
            m.role === "quiz" ? (
              <div key={m.id} className="flex justify-start">
                <div className="w-full max-w-[92%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm bg-muted border border-border rounded-bl-sm">
                  <InlineQuiz
                    message={m}
                    conversationId={activeConversationId ?? 0}
                    onFinish={submitQuiz}
                  />
                </div>
              </div>
            ) : m.role === "clarify" ? (
              <div key={m.id} className="flex justify-start">
                <div className="w-full max-w-[92%] rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm bg-muted border border-border">
                  <InlineClarify
                    message={m}
                    busy={busy}
                    onAnswer={(a) => send(a)}
                  />
                </div>
              </div>
            ) : (
            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`group/msg max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                  m.role === "user"
                    ? "bg-primary text-white rounded-br-sm"
                    : "bg-muted border border-border rounded-bl-sm"
                }`}
              >
                {m.role === "user" ? (
                  <p className="whitespace-pre-wrap m-0">{m.content}</p>
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
                {m.role === "assistant" && (
                  <div className="flex items-center gap-2 mt-2 pt-1.5 border-t border-border/40">
                    {m.created_at && (
                      <span className="text-[10px] font-mono text-muted-foreground/70">
                        {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    )}
                    {m.id > 0 && (
                      <button
                        title="Copy"
                        onClick={() => copy(m.content, m.id)}
                        className="opacity-0 group-hover/msg:opacity-60 hover:!opacity-100 p-0.5 ml-auto"
                      >
                        {copiedId === m.id ? <Check size={11} /> : <Copy size={11} />}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
            )
          ))}
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
              <div className="rounded-2xl rounded-bl-md px-4 py-2.5 bg-muted/60 border border-border/60 text-sm text-muted-foreground">
                {liveTools.length > 0
                  ? `Using ${liveTools.map((t) => t.tool).join(", ")}…`
                  : "Thinking…"}
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

        <ChatComposer busy={busy} onSend={send} />
      </div>

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

            <button
              onClick={() => setActiveConversationId(null)}
              className="btn text-xs py-2 w-full"
            >
              <Plus size={13} /> New chat
            </button>
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
