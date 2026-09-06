// Shared tutor thread: SSE streaming send, tool visibility, and
// localStorage caching (messages per conversation + conversation list) so
// switching threads/tabs never flashes empty while revalidating.

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  getChatMessages,
  getConversations,
  sendChatStream,
  submitChatQuiz,
  type ChatMessage,
  type ChatTurn,
  type Conversation,
  type ToolCall,
  type UiContext,
} from "../api";
import { useStore, useSelectedCourse } from "../store";
import { notifyError } from "./notifications";
import { runUiActions } from "./chatUi";

const LS_CONVOS = "kb.convos";
const LS_MSGS = (id: number) => `kb.chat.${id}`;

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
      return;
    }
    const cached = readCache<ChatMessage[]>(LS_MSGS(activeConversationId));
    if (cached) setMessages(cached);
    else setMessages([]);
    getChatMessages(activeConversationId)
      .then((fresh) => {
        setMessages(fresh);
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
        const next = [...m, userMsg];
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
        // Inline quiz: the tutor generated questions this turn — render the
        // sliding card right after the reply (persisted server-side as a
        // role="quiz" message, so it also restores on reload).
        if (turn.quiz) {
          const quizMsg: ChatMessage = {
            id: turn.quiz.message_id,
            role: "quiz",
            content: "",
            tool_calls: [{ tool: "quiz", args: turn.quiz }],
            created_at: new Date().toISOString(),
          };
          setMessages((m) => {
            if (m.some((x) => x.id === quizMsg.id)) return m;
            const next = [...m, quizMsg];
            writeCache(LS_MSGS(turn.conversation_id), next);
            return next;
          });
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
    ]
  );

  return {
    conversations,
    refreshList,
    messages,
    busy,
    streamText,
    liveTools,
    send,
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
