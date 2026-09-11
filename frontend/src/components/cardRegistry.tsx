// Card registry — kind → renderer. THE extension point for inline cards:
// add the backend kind in app/agent/cards.py, add one entry here, done.
// Unknown kinds render a graceful placeholder (never crash, never vanish).

import InlineClarify from "./InlineClarify";
import InlineQuiz from "./InlineQuiz";
import InlineReview from "./InlineReview";
import InlineVideo from "./InlineVideo";
import { cardKind, type ChatMessage } from "../api";

export interface CardContext {
  conversationId: number;
  busy: boolean;
  onQuizFinish: (conversationId: number, assessmentId: number) => Promise<void>;
  onClarifyAnswer: (answer: string) => void;
}

function CardShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-[92%] rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm bg-muted border border-border">
      {children}
    </div>
  );
}

function UnknownCard({ kind }: { kind: string }) {
  return (
    <div className="text-xs text-muted-foreground">
      Unsupported card type “{kind}” — update the app to view it.
    </div>
  );
}

const RENDERERS: Record<string, (message: ChatMessage, ctx: CardContext) => React.ReactNode> = {
  quiz: (message, ctx) => (
    <InlineQuiz message={message} conversationId={ctx.conversationId} onFinish={ctx.onQuizFinish} />
  ),
  clarify: (message, ctx) => (
    <InlineClarify message={message} busy={ctx.busy} onAnswer={ctx.onClarifyAnswer} />
  ),
  review: (message) => <InlineReview message={message} />,
  video: (message) => <InlineVideo message={message} />,
};

export function renderCard(message: ChatMessage, ctx: CardContext): React.ReactNode {
  const kind = cardKind(message);
  if (!kind || kind === "todo") return null; // todo lives in the side panel
  const render = RENDERERS[kind];
  const body = render ? render(message, ctx) : <UnknownCard kind={kind} />;
  return (
    <div key={message.id} className="flex justify-start">
      <CardShell>{body}</CardShell>
    </div>
  );
}

export function isCard(message: ChatMessage): boolean {
  return cardKind(message) !== null;
}
