// Shared markdown renderer for tutor replies: GFM (tables, task lists,
// strikethrough) + LaTeX ($…$ / $$…$$) + Mermaid diagrams, with app-styled
// output. Use everywhere the tutor speaks.
//
// Robustness: the model often wraps formulas in code fences instead of
// dollar delimiters. Any code block whose content looks like LaTeX is
// rendered as display math via KaTeX instead of monospace.

import { useEffect, useId, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import katex from "katex";
import "katex/dist/katex.min.css";
import type { JSX } from "react";
import { notifyError } from "./notifications";

// Mermaid loads lazily (dynamic import) so the main bundle stays lean —
// only fetched when a reply actually contains a ```mermaid block.
let mermaidInit: Promise<typeof import("mermaid").default> | null = null;
function loadMermaid() {
  if (!mermaidInit) {
    mermaidInit = import("mermaid").then((mod) => {
      const mm = mod.default;
      mm.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict", suppressErrorRendering: true });
      return mm;
    });
  }
  return mermaidInit;
}

const LATEX_HINT =
  /\\(frac|d?frac|sum|prod|int|oint|sqrt|begin|pm|mp|infty|cdot|times|div|leq|geq|neq|approx|equiv|rightarrow|left|right|overline|underline|hat|bar|vec|dot|ddot|text|mathrm|mathcal|mathbb|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|xi|pi|sigma|phi|chi|psi|omega|Gamma|Delta|Theta|Lambda|Sigma|Phi|Omega)\b/;

function codeText(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(codeText).join("");
  return "";
}

function LatexBlock({ tex }: { tex: string }) {
  let html: string;
  try {
    html = katex.renderToString(tex, { displayMode: true, throwOnError: true, strict: false });
  } catch {
    return <code>{tex}</code>;
  }
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

function errText(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  return m.replace(/\s+/g, " ").slice(0, 160) || "syntax error";
}

function MermaidBlock({ code }: { code: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setErrorMsg(null);
    loadMermaid()
      .then((mm) => mm.render(`mmd-${id}`, code))
      .then(({ svg }) => {
        if (!cancelled) setSvg(svg);
      })
      .catch((e) => {
        if (!cancelled) setErrorMsg(errText(e));
      });
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  // Route failures through the notification system — but debounced: while the
  // tutor is still streaming, every partial frame fails to parse. The timer
  // resets on each code change, so only a settled failure toasts.
  useEffect(() => {
    if (errorMsg == null) return;
    const t = window.setTimeout(
      () => notifyError(`Diagram couldn't render — ${errorMsg}`),
      2000
    );
    return () => window.clearTimeout(t);
  }, [errorMsg, code]);

  if (errorMsg != null)
    return (
      <div className="my-2 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        Couldn't render diagram — details in the notification.
        <details className="mt-1">
          <summary className="cursor-pointer">View source</summary>
          <pre className="mt-1 overflow-x-auto"><code>{code}</code></pre>
        </details>
      </div>
    );
  if (svg == null)
    return <div className="text-xs text-muted-foreground py-2">Generating diagram…</div>;
  return (
    <div
      className="my-2 overflow-x-auto rounded-lg bg-white/90 p-3 [&_svg]:max-w-full [&_svg]:h-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function langOf(className?: string): string {
  const m = /language-([\w-]+)/.exec(className ?? "");
  return m?.[1]?.toLowerCase() ?? "";
}

function CodeBlock({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}): JSX.Element {
  const lang = langOf(className);
  const text = codeText(children).replace(/\n$/, "");
  if (lang === "mermaid" && text.trim()) return <MermaidBlock code={text} />;
  if (text && LATEX_HINT.test(text)) return <LatexBlock tex={text} />;
  return <code className={className}>{children}</code>;
}

function PreBlock({ children }: { children?: React.ReactNode }): JSX.Element {
  return <pre>{children}</pre>;
}

export default function Markdown({ text }: { text: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{ pre: PreBlock, code: CodeBlock }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
