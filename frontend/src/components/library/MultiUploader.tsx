// Multi-file upload dropzone + live queue. Loops the single-upload endpoint
// (bounded concurrency in the store), showing per-file status as it progresses.

import { useCallback, useRef, useState } from "react";
import { Upload, X, FileText, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

type FileType = "pdf" | "slides" | "notes";

function detectType(name: string): FileType {
  const lower = name.toLowerCase();
  if (lower.includes("slide") || lower.includes("lecture") || lower.includes("ppt")) return "slides";
  if (lower.includes("note") || lower.includes("cheat") || lower.includes("summary")) return "notes";
  return "pdf";
}

export interface QueuedFile {
  id: string;
  file: File;
  name: string;
  type: FileType;
  moduleId: number | null;
  status: "queued" | "uploading" | "done" | "failed";
  error?: string;
}

export function MultiUploader({
  moduleId,
  onUpload,
}: {
  moduleId: number | null;
  onUpload: (files: { file: File; name: string; type: string; moduleId: number | null }[]) => Promise<void>;
}) {
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const enqueue = useCallback((fileList: FileList | File[]) => {
    const files = Array.from(fileList);
    const items: QueuedFile[] = files.map((file) => ({
      id: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2)}`,
      file,
      name: file.name,
      type: detectType(file.name),
      moduleId,
      status: "queued",
    }));
    setQueue((prev) => [...prev, ...items]);
  }, [moduleId]);

  async function start() {
    if (busy || queue.length === 0) return;
    setBusy(true);
    try {
      // Sequential, one file at a time — mirrors the server's extraction
      // queue. Each row shows its own live status; failures stay on their row.
      for (const item of queue) {
        if (item.status !== "queued") continue;
        setQueue((prev) => prev.map((q) => (q.id === item.id ? { ...q, status: "uploading" } : q)));
        try {
          await onUpload([{ file: item.file, name: item.name, type: item.type, moduleId: item.moduleId }]);
          setQueue((prev) => prev.map((q) => (q.id === item.id ? { ...q, status: "done" } : q)));
        } catch (err) {
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id ? { ...q, status: "failed", error: (err as Error).message } : q
            )
          );
        }
      }
    } finally {
      setBusy(false);
    }
  }

  function remove(id: string) {
    setQueue((prev) => prev.filter((q) => q.id !== id));
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          enqueue(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`p-5 rounded-2xl border-2 border-dashed text-center cursor-pointer transition-all ${
          dragging
            ? "border-accent bg-primary/10 scale-[0.99]"
            : "border-border/90 bg-muted/40 hover:border-accent/40 hover:bg-card/40"
        }`}
      >
        <div className="w-10 h-10 rounded-xl bg-accent/10 text-accent border border-accent/20 flex items-center justify-center mx-auto mb-2.5">
          <Upload size={18} />
        </div>
        <div className="text-xs font-bold text-foreground">
          Drop lecture notes, slides or PDFs
        </div>
        <div className="text-[11px] text-muted-foreground mt-0.5">
          Click to browse from file manager · Multi-select supported
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.ppt,.pptx,.txt,.md,.docx"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) enqueue(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {queue.length > 0 && (
        <div className="p-3 rounded-xl bg-muted/60 border border-border/80 space-y-2">
          <div className="flex items-center justify-between text-xs pb-1 border-b border-border/60">
            <span className="font-semibold text-foreground">Queue ({queue.length})</span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={start}
                disabled={busy || !queue.some((q) => q.status === "queued")}
                className="btn px-2.5 py-1 text-[11px]"
              >
                {busy ? "Uploading..." : "Upload all"}
              </button>
              <button
                onClick={() => setQueue([])}
                disabled={busy}
                className="px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              >
                Clear
              </button>
            </div>
          </div>

          <ul className="space-y-1.5 max-h-40 overflow-y-auto pr-0.5 list-none m-0 p-0">
            {queue.map((q) => (
              <li
                key={q.id}
                className="flex items-center gap-2 p-2 rounded-lg bg-card/60 border border-border/70 text-xs"
              >
                <FileText size={13} className="text-muted-foreground flex-shrink-0" />
                <span className="flex-1 min-w-0 truncate font-medium text-foreground" title={q.name}>
                  {q.name}
                </span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                  {q.type}
                </span>

                {q.status === "uploading" && (
                  <span className="flex items-center gap-1 text-[10px] text-accent font-medium">
                    <Loader2 size={11} className="animate-spin" /> Ingesting...
                  </span>
                )}
                {q.status === "done" && (
                  <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-medium">
                    <CheckCircle2 size={11} /> Ready
                  </span>
                )}
                {q.status === "failed" && (
                  <span className="flex items-center gap-1 text-[10px] text-rose-400 font-medium" title={q.error}>
                    <AlertCircle size={11} /> Failed
                  </span>
                )}
                {q.status === "queued" && (
                  <span className="text-[10px] text-muted-foreground font-mono">Queued</span>
                )}

                <button
                  onClick={() => remove(q.id)}
                  disabled={busy}
                  className="text-muted-foreground hover:text-foreground p-0.5 rounded"
                  title="Remove from queue"
                >
                  <X size={12} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

