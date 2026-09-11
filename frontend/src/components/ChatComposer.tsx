import { useEffect, useMemo, useRef, useState } from "react";
import { Send } from "lucide-react";

const COMMANDS = [
  { command: "/new", description: "Start a new chat" },
  { command: "/history", description: "Browse past conversations" },
  { command: "/quiz", description: "Generate a practice quiz" },
  { command: "/review", description: "Revise what's due" },
  { command: "/plan", description: "Build a study plan" },
];

export default function ChatComposer({
  busy,
  onSend,
}: {
  busy: boolean;
  onSend: (text: string) => void;
}) {
  const [input, setInput] = useState("");
  const [commandIndex, setCommandIndex] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const commandMenuOpen = input.startsWith("/") && !input.includes(" ");
  const prevBusy = useRef(busy);

  // Focus was dropped (e.g. Send button disabled mid-click sends focus to
  // <body>): hand it back to the composer — but only when focus is nowhere,
  // never stealing it from something the user deliberately focused meanwhile.
  useEffect(() => {
    if (prevBusy.current && !busy && document.activeElement === document.body) {
      inputRef.current?.focus();
    }
    prevBusy.current = busy;
  }, [busy]);
  const commandMatches = useMemo(
    () => (commandMenuOpen ? COMMANDS.filter((c) => c.command.startsWith(input)) : []),
    [commandMenuOpen, input]
  );

  function submit(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    onSend(text);
  }

  return (
    <div className="border-t border-border px-5 py-3.5">
      <div className="relative">
        {commandMenuOpen && commandMatches.length > 0 && (
          <div className="absolute bottom-full left-0 mb-2 w-64 rounded-xl bg-card border border-border shadow-lg overflow-hidden z-30">
            {commandMatches.map((c, i) => (
              <button
                key={c.command}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  setInput(c.command + " ");
                  setCommandIndex(0);
                  inputRef.current?.focus();
                }}
                className={`flex items-center gap-2 w-full text-left px-3 py-2 text-xs transition-colors ${
                  i === commandIndex
                    ? "bg-accent/10 text-foreground"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                }`}
              >
                <span className="font-mono font-semibold text-accent">{c.command}</span>
                <span className="flex-1">{c.description}</span>
              </button>
            ))}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
          className="w-full mx-auto flex items-end gap-2.5"
        >
          <textarea
            id="tutor-composer"
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setCommandIndex(0);
            }}
            onKeyDown={(e) => {
              if (commandMenuOpen && commandMatches.length > 0) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setCommandIndex((i) => (i + 1) % commandMatches.length);
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setCommandIndex((i) => (i - 1 + commandMatches.length) % commandMatches.length);
                  return;
                }
                if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
                  e.preventDefault();
                  setInput(commandMatches[commandIndex].command + " ");
                  setCommandIndex(0);
                  return;
                }
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(input);
              }
            }}
            placeholder="Ask anything… (Enter to send, type / for commands)"
            rows={1}
            // readOnly (not disabled): disabling drops focus the moment the
            // turn starts, forcing a mouse click to type again. submit()
            // still ignores Enter while busy.
            readOnly={busy}
            className="text-sm flex-1 resize-none max-h-32 min-h-[40px] py-2.5"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="btn text-xs p-0 shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
            title="Send"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
