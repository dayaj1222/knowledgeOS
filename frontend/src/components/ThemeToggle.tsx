import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "../context/ThemeContext";

export default function ThemeToggle({ compact = false, collapsed = false }: { compact?: boolean; collapsed?: boolean }) {
  const { theme, resolvedTheme, setTheme } = useTheme();

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        title={resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        className="flex items-center justify-center w-full rounded-lg py-1.5 bg-surface border border-border text-muted-foreground hover:text-foreground hover:bg-surface-hover transition-colors"
      >
        {resolvedTheme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
      </button>
    );
  }

  return (
    <div
      className={`flex items-center rounded-lg p-1 bg-surface border border-border ${
        compact ? "gap-0.5 justify-between" : "gap-1"
      }`}
      role="group"
      aria-label="Select color theme"
    >
      <button
        type="button"
        onClick={() => setTheme("light")}
        title="Light theme"
        className={`flex items-center justify-center rounded-md text-xs font-medium transition-colors ${
          compact ? "p-1.5 flex-1" : "px-2.5 py-1 gap-1.5"
        } ${
          theme === "light"
            ? "bg-card text-foreground shadow-xs font-semibold"
            : "text-muted-foreground hover:text-foreground"
        }`}
      >
        <Sun size={14} />
        {!compact && <span>Light</span>}
      </button>

      <button
        type="button"
        onClick={() => setTheme("dark")}
        title="Dark theme"
        className={`flex items-center justify-center rounded-md text-xs font-medium transition-colors ${
          compact ? "p-1.5 flex-1" : "px-2.5 py-1 gap-1.5"
        } ${
          theme === "dark"
            ? "bg-card text-foreground shadow-xs font-semibold"
            : "text-muted-foreground hover:text-foreground"
        }`}
      >
        <Moon size={14} />
        {!compact && <span>Dark</span>}
      </button>

      <button
        type="button"
        onClick={() => setTheme("system")}
        title="Follow system theme"
        className={`flex items-center justify-center rounded-md text-xs font-medium transition-colors ${
          compact ? "p-1.5 flex-1" : "px-2.5 py-1 gap-1.5"
        } ${
          theme === "system"
            ? "bg-card text-foreground shadow-xs font-semibold"
            : "text-muted-foreground hover:text-foreground"
        }`}
      >
        <Monitor size={14} />
        {!compact && <span>System</span>}
      </button>
    </div>
  );
}
