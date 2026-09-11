// Shared tutor thread: SSE streaming send, tool visibility, and
// localStorage caching (messages per conversation + conversation list) so
// switching threads/tabs never flashes empty while revalidating.

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  createStudyLog,
  getChatMessages,
  getConversations,
  sendChatStream,
  submitChatQuiz,
  type ChatMessage,
  type ChatTurn,
  type Conversation,
  type TodoPayload,
  type ToolCall,
  type UiContext,
} from "../api";
import { useStore, useSelectedCourse } from "../store";
import { notifyError } from "./notifications";
import { runUiActions } from "./chatUi";

const LS_CONVOS = "kb.convos";
const LS_MSGS = (id: number) => `kb.chat.${id}`;
const LS_TIMER = "kb.timer";

export interface ActiveTimer {
  topicId: number;
  topicName: string;
  label: string;
  startedAt: number;
}

function readCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeCache(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota or private mode — caching is best-effort.
  }
}

export function dropThreadCache(id: number) {
  try {
    localStorage.removeItem(LS_MSGS(id));
  } catch {
    // best-effort
  }
}

function extractTodo(msgs: ChatMessage[]): TodoPayload | null {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    // New card shape + legacy cached shapes (pre-cards-table threads).
    const args = (m.card?.payload
      ?? m.tool_calls?.[0]?.args
      ?? {}) as Record<string, unknown>;
    const isTodo = (m.role === "card" && m.card?.kind === "todo") || m.role === "todo";
    if (!isTodo) continue;
    if (Array.isArray(args.todos)) return { message_id: m.id, ...(args as object) } as TodoPayload;
  }
  return null;
}

function makeCard(id: number, kind: string, payload: unknown): ChatMessage {
  return {
    id,
    role: "card",
    content: "",
    card: { kind, payload: (payload ?? {}) as Record<string, unknown> },
    created_at: new Date().toISOString(),
  };
}

export function useChatThread() {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    selectCourse,
    reloadCourses,
    reloadTree,
    selectedCourseId,
    activeConversationId,
    setActiveConversationId,
  } = useStore();
  const selectedCourse = useSelectedCourse();

  // Conversation list: cache first, revalidate in background.
  const [conversations, setConversations] = useState<Conversation[]>(
    () => readCache<Conversation[]>(LS_CONVOS) ?? []
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [liveTools, setLiveTools] = useState<ToolCall[]>([]);
  // Study timer: tutor-started via start_timer, renders as a live pill.
  // Persisted so a reload keeps counting from the original start.
  const [timer, setTimer] = useState<ActiveTimer | null>(
    () => readCache<ActiveTimer>(LS_TIMER)
  );
  // Agent todo list: latest update_todo payload (side-panel graph).
  // Derived from turn.todo on send + last todo card on load.
  const [todo, setTodo] = useState<TodoPayload | null>(null);
  // Ref mirror — the send() callback reads the live timer without going stale.
  const timerRef = useRef<ActiveTimer | null>(readCache<ActiveTimer>(LS_TIMER));

  const persistTimer = useCallback((t: ActiveTimer | null) => {
    timerRef.current = t;
    setTimer(t);
    try {
      if (t) localStorage.setItem(LS_TIMER, JSON.stringify(t));
      else localStorage.removeItem(LS_TIMER);
    } catch {
      // best-effort
    }
  }, []);

  const refreshList = useCallback(async () => {
    try {
      const list = await getConversations();
      setConversations(list);
      writeCache(LS_CONVOS, list);
    } catch (e) {
      notifyError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  // Active thread: show cache instantly, then revalidate.
  useEffect(() => {
    if (activeConversationId == null) {
      setMessages([]);
      setTodo(null);
      return;
    }
    const cached = readCache<ChatMessage[]>(LS_MSGS(activeConversationId));
    if (cached) {
      setMessages(cached);
      setTodo(extractTodo(cached));
    } else {
      setMessages([]);
      setTodo(null);
    }
    getChatMessages(activeConversationId)
      .then((fresh) => {
        setMessages(fresh);
        setTodo(extractTodo(fresh));
        writeCache(LS_MSGS(activeConversationId), fresh);
      })
      .catch((e) => notifyError((e as Error).message));
  }, [activeConversationId]);

  const send = useCallback(
    async (text: string) => {
      const msg = text.trim();
      if (!msg || busy) return;
      setBusy(true);
      setStreamText("");
      setLiveTools([]);
      // UI STATE for the tutor: where the student is right now.
      const uiContext: UiContext = {
        route: location.pathname,
        course_id: selectedCourseId,
        course_name: selectedCourse?.name ?? null,
      };
      const userMsg: ChatMessage = { id: -Date.now(), role: "user", content: msg };
      setMessages((m) => {
        // Mirror the server: this answer closes the most recent still-open
        // clarify card (server stamps it on arrival; reload wins on conflict).
        // Handles both card shapes and legacy cached role="clarify" rows.
        let lastOpen = -1;
        m.forEach((x, i) => {
          const kind = x.role === "card" ? x.card?.kind : x.role;
          if (kind !== "clarify") return;
          const a = (x.card?.payload ?? x.tool_calls?.[0]?.args ?? {}) as { completed?: boolean };
          if (!a.completed) lastOpen = i;
        });
        const stamped = lastOpen === -1 ? m : m.map((x, i) => {
          if (i !== lastOpen) return x;
          const a = (x.card?.payload ?? x.tool_calls?.[0]?.args ?? {}) as Record<string, unknown>;
          const stampedArgs = { ...a, completed: true, answer: msg };
          if (x.role === "card" && x.card) {
            return { ...x, card: { ...x.card, payload: stampedArgs } };
          }
          return { ...x, tool_calls: [{ tool: "clarify", args: stampedArgs }] };
        });
        const next = [...stamped, userMsg];
        if (activeConversationId != null) writeCache(LS_MSGS(activeConversationId), next);
        return next;
      });
      try {
        const turn = await sendChatStream(msg, activeConversationId, (type, data) => {
          if (type === "token") setStreamText((t) => t + String(data.text ?? ""));
          else if (type === "tool")
            setLiveTools((ts) => [
              ...ts,
              {
                tool: String(data.tool),
                args: data.args,
                result_preview: (data.result_preview as string) ?? null,
              },
            ]);
        }, uiContext);
        if (activeConversationId == null) {
          setActiveConversationId(turn.conversation_id);
          setConversations((c) => {
            const next = [{ id: turn.conversation_id, title: msg.slice(0, 60) }, ...c];
            writeCache(LS_CONVOS, next);
            return next;
          });
        }
        const assistant: ChatMessage = {
          id: Date.now(),
          role: "assistant",
          content: turn.reply,
          tool_calls: turn.tool_calls,
          created_at: new Date().toISOString(),
        };
        setMessages((m) => {
          const next = [...m, assistant];
          writeCache(LS_MSGS(turn.conversation_id), next);
          return next;
        });
        // Inline cards (quiz/clarify/review/todo/video): one construction
        // path for every kind — server persists them to the cards table,
        // so they restore on reload in display order.
        const newCards: { kind: string; payload: unknown }[] = [];
        if (turn.quiz) newCards.push({ kind: "quiz", payload: turn.quiz });
        if (turn.clarify) newCards.push({ kind: "clarify", payload: turn.clarify });
        if (turn.review) newCards.push({ kind: "review", payload: turn.review });
        if (turn.todo) newCards.push({ kind: "todo", payload: turn.todo });
        if (turn.video) newCards.push({ kind: "video", payload: turn.video });
        for (const { kind, payload } of newCards) {
          const messageId = (payload as { message_id: number }).message_id;
          const cardMsg = makeCard(messageId, kind, payload);
          if (kind === "todo") setTodo(payload as TodoPayload);
          setMessages((m) => {
            if (m.some((x) => x.id === cardMsg.id)) return m;
            const next = [...m, cardMsg];
            writeCache(LS_MSGS(turn.conversation_id), next);
            return next;
          });
        }
        // Study timer: start replaces any running timer; stop logs the
        // elapsed session as a study log (tutor's reply covers the chat side).
        if (turn.timer?.action === "start" && turn.timer.topic_id != null) {
          persistTimer({
            topicId: turn.timer.topic_id,
            topicName: turn.timer.topic_name ?? "",
            label: turn.timer.label ?? turn.timer.topic_name ?? "Study session",
            startedAt: Date.now(),
          });
        } else if (turn.timer?.action === "stop") {
          const t = timerRef.current;
          persistTimer(null);
          if (t) {
            const minutes = Math.floor((Date.now() - t.startedAt) / 60000);
            if (minutes >= 1) {
              createStudyLog({ topic_id: t.topicId, minutes_spent: minutes }).catch(() => {});
            }
          }
        }
        runUiActions(turn.ui_actions ?? [], {
          navigate,
          selectCourse,
          reloadCourses,
          reloadTree,
          selectedCourseId,
        });
    } catch (e) {
      const detail = (e as Error).message;
      notifyError(detail);
      setMessages((m) => [
        ...m,
        { id: Date.now(), role: "assistant", content: `Something went wrong — ${detail}` },
      ]);
    } finally {
        setBusy(false);
        setStreamText("");
        setLiveTools([]);
      }
    },
    [
      busy,
      activeConversationId,
      setActiveConversationId,
      navigate,
      location.pathname,
      selectCourse,
      reloadCourses,
      reloadTree,
      selectedCourseId,
      selectedCourse,
      persistTimer,
    ]
  );

  // Manual stop from the timer pill: log the session, then tell the tutor
  // in plain words so it responds naturally (record_understanding etc.).
  // Under a minute of study is noise — stop silently without logging.
  const stopTimer = useCallback(async () => {
    const t = timerRef.current;
    persistTimer(null);
    if (!t) return;
    const minutes = Math.floor((Date.now() - t.startedAt) / 60000);
    if (minutes < 1) return;
    try {
      await createStudyLog({ topic_id: t.topicId, minutes_spent: minutes });
    } catch {
      // best-effort; the chat message still carries the session
    }
    await send(`Finished studying ${t.label} for ${minutes} min`);
  }, [persistTimer, send]);

  return {
    conversations,
    refreshList,
    messages,
    busy,
    streamText,
    liveTools,
    send,
    timer,
    stopTimer,
    todo,
    submitQuiz: async (conversationId: number, assessmentId: number) => {
      // Per-card answers were graded silently already; this runs the hidden
      // tutor debrief and appends ONLY the recommendation to the thread.
      const turn: ChatTurn = await submitChatQuiz(conversationId, assessmentId);
      const debrief: ChatMessage = {
        id: Date.now(),
        role: "assistant",
        content: turn.reply,
        tool_calls: turn.tool_calls,
        created_at: new Date().toISOString(),
      };
      if (turn.todo) setTodo(turn.todo);
      setMessages((m) => {
        const next = [...m, debrief];
        writeCache(LS_MSGS(turn.conversation_id), next);
        return next;
      });
      runUiActions(turn.ui_actions ?? [], {
        navigate,
        selectCourse,
        reloadCourses,
        reloadTree,
        selectedCourseId,
      });
    },
    retry: async () => {
      if (busy) return;
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      if (!lastUser) return;
      // Drop the failed assistant reply ahead of the resend.
      setMessages((m) => m.filter((x) => !(x.role === "assistant" && x.id > lastUser.id)));
      await send(lastUser.content);
    },
  };
}
