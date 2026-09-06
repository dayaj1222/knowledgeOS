// A selectable course in the sidebar list.
import { BookOpen } from "lucide-react";
import type { Course } from "../../api";

function isPlaceholder(course: Course): boolean {
  const name = course.name?.trim() ?? "";
  const code = course.code?.trim() ?? "";
  return !name || name.length <= 1 || (!code && !name);
}

export function CourseListItem({
  course,
  selected,
  onSelect,
}: {
  course: Course;
  selected: boolean;
  onSelect: (id: number) => void;
}) {
  const placeholder = isPlaceholder(course);
  const displayName = placeholder ? "Untitled course" : course.name;
  const displayCode = placeholder ? "click to edit" : (course.code || "");
  
  return (
    <li>
      <button
        onClick={() => onSelect(course.id)}
        title={`${course.name || "Untitled"} (${course.code || "no code"})`}
        className={`w-full text-left p-3 rounded-xl transition-all flex items-center gap-3 border ${
          selected
            ? "bg-primary/15 border-accent/40 shadow-sm text-foreground"
            : placeholder
            ? "bg-card/40 border-dashed border-border text-muted-foreground hover:border-border"
            : "bg-card/60 border-border/80 text-foreground hover:border-border hover:bg-card"
        }`}
      >
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
            selected
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-muted/80 text-muted-foreground"
          }`}
        >
          <BookOpen size={16} strokeWidth={selected ? 2.2 : 1.8} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-xs text-foreground truncate flex items-center justify-between gap-1">
            <span className="truncate">{displayName}</span>
            {displayCode && (
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-muted text-foreground border border-border/60 flex-shrink-0">
                {displayCode}
              </span>
            )}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-2">
            <span>{course.module_count ?? 0} modules</span>
            <span className="w-1 h-1 rounded-full bg-muted" />
            <span>{course.topic_count ?? 0} topics</span>
          </div>
        </div>
      </button>
    </li>
  );
}

