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
  onSend: (text: string, image?: string | null) => void;
}) {
  const [input, setInput] = useState("");
  const [commandIndex, setCommandIndex] = useState(0);
  // One attached image per message (proxy forwards one per turn). Paste or
  // drop to attach; a new paste replaces. Downscaled client-side ≤1600px.
  const [image, setImage] = useState<string | null>(null);
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

  function fileToDataUrl(file: File): Promise<string | null> {
    if (!file.type.startsWith("image/")) return Promise.resolve(null);
    return new Promise((resolve) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        const max = 1600;
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext("2d")?.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        resolve(null);
      };
      img.src = url;
    });
  }

  async function attachFiles(files: FileList | File[] | null) {
    if (!files) return;
    for (const f of Array.from(files)) {
      const dataUrl = await fileToDataUrl(f);
      if (dataUrl) {
        setImage(dataUrl);
        return; // one image per message
      }
    }
  }

  function submit(text: string) {
    if ((!text.trim() && !image) || busy) return;
    setInput("");
    const attached = image;
    setImage(null);
    onSend(text, attached);
  }

  return (
    <div
      className="border-t border-border px-5 py-3.5"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        void attachFiles(e.dataTransfer.files);
      }}
    >
      {image && (
        <div className="relative inline-block mb-2">
          <img src={image} alt="Attached" className="h-16 rounded-lg border border-border" />
          <button
            type="button"
            onClick={() => setImage(null)}
            title="Remove image"
            className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-muted text-muted-foreground hover:text-foreground border border-border text-xs leading-none"
          >
            ×
          </button>
        </div>
      )}
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
            onPaste={(e) => {
              void attachFiles(e.clipboardData.files);
            }}
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
            // An image can be the entire prompt, so text is not required to
            // enable sending once an attachment has been prepared.
            disabled={busy || (!input.trim() && !image)}
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
