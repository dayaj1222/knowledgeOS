// Shared tutor thread on React Query: the thread and conversation list are
// server state (localStorage seeds instant first paint + persists offline).
// Ephemeral UI (busy, stream text, live tools, timer pill) stays in useState.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  createStudyLog,
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
import {
  LS_CONVOS,
  LS_MSGS,
  useConversations,
  useThreadMessages,
  writeLS,
} from "../hooks/queries";
import { notifyError } from "./notifications";
import { runUiActions } from "./chatUi";

const LS_TIMER = "kb.timer";

export interface ActiveTimer {
  topicId: number;
  topicName: string;
  label: string;
  startedAt: number;
}

function readTimer(): ActiveTimer | null {
  try {
    const raw = localStorage.getItem(LS_TIMER);
    return raw ? (JSON.parse(raw) as ActiveTimer) : null;
  } catch {
    return null;
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
  const queryClient = useQueryClient();
  const {
    selectCourse,
    reloadCourses,
    reloadTree,
    selectedCourseId,
    activeConversationId,
    setActiveConversationId,
  } = useStore();
  const selectedCourse = useSelectedCourse();

  const convosQuery = useConversations();
  const threadQuery = useThreadMessages(activeConversationId);
  const conversations = useMemo(() => convosQuery.data ?? [], [convosQuery.data]);
  // Pin for the NEXT new conversation (new-chat menu / Library entry).
  // Stamped server-side on the first message; cleared once created.
  const [pendingPin, setPendingPin] = useState<{ id: number; name: string } | null>(null);
  // Library entry: navigation state carries the module to pin.
  const navPin = (location.state as { pinModule?: { id: number; name: string } } | null)?.pinModule;
  useEffect(() => {
    if (navPin != null) {
      setPendingPin(navPin);
      setActiveConversationId(null);
      setSeed([]);
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [navPin]);
  // New conversation (no id yet): optimistic seed shown until the server
  // answers with the real thread. Cleared on turn completion or switch.
  const [seed, setSeed] = useState<ChatMessage[]>([]);
  const messages = useMemo(
    () => (activeConversationId == null ? seed : (threadQuery.data ?? [])),
    [activeConversationId, seed, threadQuery.data]
  );
  // Todo derives from the latest todo card — no separate state to sync.
  const todo = useMemo(() => extractTodo(messages), [messages]);

  const [busy, setBusy] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [liveTools, setLiveTools] = useState<ToolCall[]>([]);
  // Study timer: tutor-started via start_timer, renders as a live pill.
  // Persisted so a reload keeps counting from the original start.
  const [timer, setTimer] = useState<ActiveTimer | null>(readTimer);
  // Ref mirror — the send() callback reads the live timer without going stale.
  const timerRef = useRef<ActiveTimer | null>(readTimer());

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

  // Append/rewrite helper: React Query cache is the source of truth,
  // localStorage mirrors it for instant reloads.
  const updateThread = useCallback(
    (conversationId: number, updater: (prev: ChatMessage[]) => ChatMessage[]) => {
      const next = queryClient.setQueryData<ChatMessage[]>(
        ["thread", conversationId],
        (prev) => updater(prev ?? [])
      ) as ChatMessage[] | undefined;
      if (next) writeLS(LS_MSGS(conversationId), next);
    },
    [queryClient]
  );

  const refreshList = useCallback(async () => {
    try {
      const list = await convosQuery.refetch();
      if (list.data) writeLS(LS_CONVOS, list.data);
    } catch (e) {
      notifyError((e as Error).message);
    }
  }, [convosQuery]);

  useEffect(() => {
    setSeed([]);
  }, [activeConversationId]);

  useEffect(() => {
    if (convosQuery.error) notifyError((convosQuery.error as Error).message);
  }, [convosQuery.error]);

  useEffect(() => {
    if (threadQuery.error && activeConversationId != null) {
      notifyError((threadQuery.error as Error).message);
    }
  }, [threadQuery.error, activeConversationId]);

  const send = useCallback(
    async (text: string, image?: string | null) => {
      const msg = text.trim();
      if ((!msg && !image) || busy) return;
      setBusy(true);
      setStreamText("");
      setLiveTools([]);
      // UI STATE for the tutor: where the student is right now.
      // Stored pin wins on existing threads (server is source of truth);
      // pendingPin stamps brand-new conversations on their first message.
      const activeConvo = conversations.find((c) => c.id === activeConversationId);
      const uiContext: UiContext = {
        route: location.pathname,
        course_id: selectedCourseId,
        course_name: selectedCourse?.name ?? null,
        module_id: activeConvo?.module_id ?? pendingPin?.id ?? null,
      };
      const userMsg: ChatMessage = {
        id: -Date.now(), role: "user",
        content: msg,
        images: image ? [image] : null,
      };
      const targetConvo = activeConversationId;
      if (targetConvo != null) {
        updateThread(targetConvo, (m) => {
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
          return [...stamped, userMsg];
        });
      } else {
        // New conversation: seed a local-only thread until the server
        // answers with the real conversation id.
        setSeed([userMsg]);
      }
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
        }, uiContext, image ? [image] : undefined);
        if (activeConversationId == null) {
          setActiveConversationId(turn.conversation_id);
          setSeed([]);
          const stamped = pendingPin;
          setPendingPin(null);
          queryClient.setQueryData(
            ["conversations"],
            (prev: Conversation[] | undefined) => {
              const next = [{
                id: turn.conversation_id,
                title: msg.slice(0, 60) || "Image question",
                module_id: stamped?.id ?? null,
                module_name: stamped?.name ?? null,
              }, ...(prev ?? [])];
              writeLS(LS_CONVOS, next);
              return next;
            }
          );
          // Move the locally-seeded user message into the real thread.
          updateThread(turn.conversation_id, () => [userMsg]);
        }
        const assistant: ChatMessage = {
          id: Date.now(),
          role: "assistant",
          content: turn.reply,
          tool_calls: turn.tool_calls,
          created_at: new Date().toISOString(),
        };
        updateThread(turn.conversation_id, (m) => [...m, assistant]);
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
          updateThread(turn.conversation_id, (m) => {
            if (m.some((x) => x.id === cardMsg.id)) return m;
            return [...m, cardMsg];
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
        // Thread changed server-side (cards persisted) — revalidate in background.
        queryClient.invalidateQueries({ queryKey: ["thread", turn.conversation_id] });
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
      } catch (e) {
        const detail = (e as Error).message;
        notifyError(detail);
        const failedTurn: ChatMessage = {
          id: Date.now(),
          role: "assistant",
          content: `Something went wrong — ${detail}`,
        };
        if (activeConversationId != null) {
          updateThread(activeConversationId, (m) => [...m, failedTurn]);
        } else {
          setSeed((s) => [...s, failedTurn]);
        }
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
      pendingPin,
      conversations,
      persistTimer,
      queryClient,
      updateThread,
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
    // Pin state: existing threads read the stored pin (server truth);
    // new threads preview pendingPin until the first message stamps it.
    activePin: activeConversationId == null
      ? pendingPin
      : (() => {
          const c = conversations.find((x) => x.id === activeConversationId);
          return c?.module_id != null
            ? { id: c.module_id, name: c.module_name ?? `#${c.module_id}` }
            : null;
        })(),
    pendingPin,
    startPinned: (pin: { id: number; name: string } | null) => {
      setPendingPin(pin);
      setActiveConversationId(null);
      setSeed([]);
    },
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
      updateThread(turn.conversation_id, (m) => [...m, debrief]);
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
      if (!lastUser || activeConversationId == null) return;
      // Drop the failed assistant reply ahead of the resend.
      updateThread(activeConversationId, (m) =>
        m.filter((x) => !(x.role === "assistant" && x.id > lastUser.id))
      );
      await send(lastUser.content);
    },
  };
}
