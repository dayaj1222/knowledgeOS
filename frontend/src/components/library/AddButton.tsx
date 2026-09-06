// A collapsed "+" button that expands into an inline single-input form.
import { useState } from "react";
import { Plus, X } from "lucide-react";
import { useNotify } from "../notifications";

export function AddButton({
  label,
  placeholder,
  onAdd,
  style,
  indent,
}: {
  label: string;
  placeholder: string;
  onAdd: (value: string) => Promise<void>;
  style?: React.CSSProperties;
  indent?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const notify = useNotify();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const v = value.trim();
    if (!v || busy) return;
    setBusy(true);
    try {
      await onAdd(v);
      setValue("");
      setOpen(false);
    } catch (err) {
      notify.error(`Failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full py-2 px-3 rounded-xl border border-dashed border-border/90 text-muted-foreground hover:text-accent hover:border-accent/40 hover:bg-card/40 text-xs font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer"
        style={{ ...style, marginLeft: indent ? 16 : 0 }}
      >
        <Plus size={13} />
        <span>{label}</span>
      </button>
    );
  }

  return (
    <form
      onSubmit={submit}
      className="flex items-center gap-1.5 p-1 rounded-xl bg-muted/80 border border-accent/40"
      style={{ ...style, marginLeft: indent ? 16 : 0 }}
    >
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        autoFocus
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
        className="flex-1 text-xs py-1 px-2.5 bg-transparent border-0 focus:ring-0 text-foreground placeholder:text-muted-foreground"
      />
      <button
        type="submit"
        disabled={busy || !value.trim()}
        className="px-3 py-1 bg-primary hover:bg-accent disabled:opacity-50 text-primary-foreground text-xs font-semibold rounded-lg transition-colors cursor-pointer"
      >
        {busy ? "..." : "Add"}
      </button>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="p-1 text-muted-foreground hover:text-foreground rounded-lg cursor-pointer"
      >
        <X size={13} />
      </button>
    </form>
  );
}

