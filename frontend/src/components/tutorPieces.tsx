import { MessageCircle } from "lucide-react";
import type { Course } from "../api";

export const SUGGESTIONS = [
  "Quiz me on my weakest topic",
  "What should I revise today?",
  "Explain the last thing I got wrong",
  "Plan my study week",
];

export function ModulePickList({
  courses,
  allCourseTrees,
  onPick,
}: {
  courses: Course[];
  allCourseTrees: Record<number, { moduleId: number; moduleName: string }[]>;
  onPick: (module: { id: number; name: string } | null) => void;
}) {
  return (
    <>
      {courses.map((course) => {
        const entries = allCourseTrees[course.id] ?? [];
        if (entries.length === 0) return null;
        return (
          <div key={course.id}>
            <div className="px-2.5 pt-2 pb-0.5 text-[10px] font-mono uppercase text-muted-foreground truncate">
              {course.code || course.name}
            </div>
            {entries.map((entry) => (
              <button
                key={entry.moduleId}
                onClick={() => onPick({ id: entry.moduleId, name: entry.moduleName })}
                className="w-full text-left text-xs px-2.5 py-2 rounded-lg hover:bg-muted truncate"
              >
                {entry.moduleName}
              </button>
            ))}
          </div>
        );
      })}
      <button
        onClick={() => onPick(null)}
        className="w-full text-left text-xs px-2.5 py-2 rounded-lg hover:bg-muted text-muted-foreground flex items-center gap-1.5"
      >
        <MessageCircle size={12} /> Unpinned chat
      </button>
    </>
  );
}

export function UserText({ text }: { text: string }) {
  const lines = text.split("\n");
  const quote: string[] = [];
  let i = 0;
  while (i < lines.length && lines[i].startsWith("> ")) {
    quote.push(lines[i].slice(2));
    i++;
  }
  while (i < lines.length && lines[i].trim() === "") i++;
  const rest = lines.slice(i).join("\n");
  if (quote.length === 0) return <p className="whitespace-pre-wrap m-0">{text}</p>;
  const flat = quote.join("\n");
  return (
    <>
      <div className="rounded-lg bg-black/15 border-l-2 border-white/60 pl-2.5 pr-2 py-1 mb-1.5 text-[13px] leading-snug opacity-90 whitespace-pre-wrap">
        {flat.slice(0, 300)}
        {flat.length > 300 ? "…" : ""}
      </div>
      {rest && <p className="whitespace-pre-wrap m-0">{rest}</p>}
    </>
  );
}
