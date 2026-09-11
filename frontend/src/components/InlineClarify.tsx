// In-chat clarify card: the tutor's disambiguating question rendered as
// tappable options plus optional free text. Answering sends the answer as a
// normal chat message (the server stamps this card completed + answered, so
// reloads render it read-only).

import { useState } from "react";
import { Check, HelpCircle, Send } from "lucide-react";
import type { ChatMessage } from "../api";
import { cardPayload } from "../api";

interface ClarifyArgs {
  question?: string;
  options?: string[];
  allow_free_text?: boolean;
  completed?: boolean;
  answer?: string | null;
}

export default function InlineClarify({
  message,
  onAnswer,
  busy,
}: {
  message: ChatMessage;
  onAnswer: (answer: string) => void;
  busy: boolean;
}) {
  const args = (cardPayload(message)) as ClarifyArgs;
  const question = args.question ?? "";
  const options = args.options ?? [];
  const allowFreeText = args.allow_free_text !== false;
  const done = args.completed === true;
  const [text, setText] = useState("");

  function answer(value: string) {
    const v = value.trim();
    if (!v || busy || done) return;
    setText("");
    onAnswer(v);
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-start gap-2">
        <HelpCircle size={15} className="mt-0.5 shrink-0 text-accent" />
        <p className="text-sm font-medium text-foreground m-0">{question}</p>
      </div>

      {options.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {options.map((o) => {
            const selected = done && args.answer === o;
            return (
              <button
                key={o}
                onClick={() => answer(o)}
                disabled={busy || done}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors disabled:cursor-default ${
                  selected
                    ? "bg-accent/15 border-accent/50 text-foreground font-medium"
                    : "bg-card border-border text-foreground hover:border-accent/50 hover:bg-accent/10 disabled:hover:border-border disabled:hover:bg-card"
                }`}
              >
                {selected && <Check size={11} className="inline mr-1 -mt-0.5" />}
                {o}
              </button>
            );
          })}
        </div>
      )}

      {allowFreeText && !done && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            answer(text);
          }}
          className="flex items-center gap-1.5"
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Or type your own answer…"
            disabled={busy}
            className="text-xs flex-1 rounded-lg bg-card border border-border/70 py-1.5 px-2.5 text-foreground placeholder:text-muted-foreground/60 focus:border-accent/60"
          />
          <button
            type="submit"
            disabled={busy || !text.trim()}
            title="Send answer"
            className="p-1.5 rounded-lg text-accent hover:bg-accent/10 disabled:opacity-40"
          >
            <Send size={13} />
          </button>
        </form>
      )}

      {done && args.answer && (
        <p className="text-xs text-muted-foreground m-0">
          You answered: <span className="text-foreground font-medium">{args.answer}</span>
        </p>
      )}
    </div>
  );
}
