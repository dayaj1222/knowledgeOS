// Global tutor bubble + compact drawer. Shares the active conversation with
// the /tutor page via the shared thread hook (streaming + cache), so moving
// between tabs continues the same thread. Hidden on /tutor itself.

import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { MessageSquare, Plus, Send, X } from "lucide-react";
import { useStore } from "../store";
import { useChatThread } from "./useChatThread";
import Markdown from "./Markdown";
import ToolCalls from "./ToolCalls";

export default function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { setActiveConversationId } = useStore();
  const {
    messages,
    busy,
    streamText,
    liveTools,
    send: sendStream,
  } = useChatThread();

  const hidden = location.pathname === "/tutor";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, streamText, open]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    await sendStream(text);
  }

  if (hidden) return null;

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        title="Tutor"
        className="fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full bg-primary text-white shadow-lg flex items-center justify-center hover:opacity-90 transition-opacity"
      >
        {open ? <X size={20} /> : <MessageSquare size={20} />}
      </button>

      {open && (
        <div className="fixed top-0 right-0 bottom-0 z-40 w-full max-w-[400px] bg-card border-l border-border shadow-xl flex flex-col animate-fadeIn">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
            <span className="text-sm font-semibold text-foreground">Tutor</span>
            <div className="ml-auto flex items-center gap-1.5">
              <button
                onClick={() => setActiveConversationId(null)}
                title="New chat"
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted"
              >
                <Plus size={14} />
              </button>
              <button
                onClick={() => navigate("/tutor")}
                title="Open full chat"
                className="text-xs font-semibold text-accent px-2 py-1.5 rounded-lg hover:bg-muted"
              >
                Full chat
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 && !busy && (
              <p className="text-xs text-muted-foreground text-center py-8">
                Ask about your material, request a quiz, or say "plan my week".
              </p>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-[13px] leading-relaxed ${
                    m.role === "user"
                      ? "bg-primary text-white"
                      : "bg-muted/70 text-foreground border border-border/60"
                  }`}
                >
                  {m.role === "user" ? (
                    <p className="whitespace-pre-wrap m-0">{m.content}</p>
                  ) : (
                    <Markdown text={m.content} />
                  )}
                  <ToolCalls calls={m.tool_calls ?? []} />
                </div>
              </div>
            ))}
            {busy && streamText && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-xl px-3 py-2 text-[13px] bg-muted/70 border border-border/60">
                  <Markdown text={streamText} />
                  <span className="inline-block w-1.5 h-3 ml-1 -mb-0.5 bg-accent/70 animate-pulse" />
                </div>
              </div>
            )}
            {busy && !streamText && (
              <p className="text-xs text-muted-foreground">
                {liveTools.length > 0 ? `Using ${liveTools.map((t) => t.tool).join(", ")}…` : "Thinking…"}
              </p>
            )}
            <div ref={bottomRef} />
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-center gap-2 px-3 py-3 border-t border-border"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask the tutor…"
              className="text-[13px] flex-1"
              disabled={busy}
              autoFocus
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="btn text-xs p-2.5 shrink-0"
              title="Send"
            >
              <Send size={14} />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
