import { BASE_URL, USER_ID, request } from "./core/client";

export function chatImageUrl(image: string): string {
  return image.startsWith("/storage/") ? `${BASE_URL.replace(/\/api$/, "")}${image}` : image;
}

export interface UiAction { action: string; params: Record<string, unknown> }
export interface ToolCall { tool: string; args: unknown; result_preview?: string | null }
export interface QuizQuestion { id: number; topic_id: number; text: string; type: string; expected_key_points?: unknown[] }
export interface InlineQuizPayload { message_id: number; assessment_id: number; questions: QuizQuestion[] }
export interface InlineClarifyPayload { message_id: number; question: string; options: string[]; allow_free_text: boolean; completed?: boolean; answer?: string | null }
export interface ReviewItem { topic_id: number; topic_name: string; prompt: string; key_points: string[] }
export interface InlineReviewPayload { message_id: number; items: ReviewItem[] }
export interface TimerPayload { action: "start" | "stop"; topic_id?: number; topic_name?: string; label?: string }
export interface VideoItem { video_id: string; title: string; url: string; embed_url: string; thumbnail: string; snippet?: string; relevance?: number; verified?: boolean; verify_note?: string; start_seconds?: number; timestamp_label?: string; timestamp_excerpt?: string; seek_confidence?: "high" | "medium" }
export interface VideoPayload { message_id: number; videos: VideoItem[] }
export interface TodoItem { content: string; status: "pending" | "in_progress" | "completed"; activeForm?: string; weight?: number }
export interface TodoPayload { message_id: number; todos: TodoItem[]; total: number; completed: number; current?: string | null; current_active?: string | null }
export interface ChatTurn { conversation_id: number; reply: string; tool_calls: ToolCall[]; ui_actions: UiAction[]; quiz?: InlineQuizPayload | null; clarify?: InlineClarifyPayload | null; review?: InlineReviewPayload | null; timer?: TimerPayload | null; todo?: TodoPayload | null; video?: VideoPayload | null }
export interface Conversation { id: number; title: string; module_id?: number | null; module_name?: string | null }
export interface ChatMessage { id: number; role: string; content: string; images?: string[] | null; tool_calls?: ToolCall[] | null; card?: { kind: string; payload: Record<string, unknown> } | null; created_at?: string | null }
export interface UiContext { route: string; course_id?: number | null; course_name?: string | null; detail?: string | null; module_id?: number | null; reply_target?: { source: "user" | "tutor"; text: string } }
export interface TutorMemory { id: number; key: string; value: string }

export function cardPayload(message: ChatMessage): Record<string, unknown> { return (message.card?.payload ?? (message.tool_calls?.[0]?.args as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>; }
export function cardKind(message: ChatMessage): string | null { if (message.role === "card" && message.card) return message.card.kind; if (["quiz", "clarify", "review", "video", "todo"].includes(message.role)) return message.role; return null; }
export const sendChat = (message: string, conversationId?: number | null, uiContext?: UiContext | null, images?: string[]) => request<ChatTurn>(`/chat`, { method: "POST", body: JSON.stringify({ user_id: USER_ID, conversation_id: conversationId ?? null, message, ui_context: uiContext ?? null, images: images ?? null }) });

export async function sendChatStream(message: string, conversationId: number | null | undefined, onEvent: (type: string, data: Record<string, unknown>) => void, uiContext?: UiContext | null, images?: string[]): Promise<ChatTurn> {
  const res = await fetch(`${BASE_URL}/chat/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: USER_ID, conversation_id: conversationId ?? null, message, ui_context: uiContext ?? null, images: images ?? null }) });
  if (!res.ok || !res.body) throw new Error(`Chat stream failed: ${res.status}`);
  const reader = res.body.getReader(); const decoder = new TextDecoder(); let buf = ""; let done: ChatTurn | null = null;
  for (;;) {
    const { value, done: eof } = await reader.read(); if (value) buf += decoder.decode(value, { stream: true }); buf = buf.replace(/\r\n/g, "\n");
    for (;;) { const sep = buf.indexOf("\n\n"); if (sep === -1) break; const frame = buf.slice(0, sep); buf = buf.slice(sep + 2); const event = (/^event:\s*(.*)$/m.exec(frame) ?? [])[1]?.trim() ?? "message"; const lines = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()); if (!lines.length) continue; let data: Record<string, unknown>; try { data = JSON.parse(lines.join("\n")) as Record<string, unknown>; } catch { continue; }
      if (event === "done") done = { conversation_id: data.conversation_id as number, reply: data.reply as string, tool_calls: (data.tool_calls as ToolCall[]) ?? [], ui_actions: (data.ui_actions as UiAction[]) ?? [], quiz: (data.quiz as InlineQuizPayload | null) ?? null, clarify: (data.clarify as InlineClarifyPayload | null) ?? null, review: (data.review as InlineReviewPayload | null) ?? null, timer: (data.timer as TimerPayload | null) ?? null, todo: (data.todo as TodoPayload | null) ?? null, video: (data.video as VideoPayload | null) ?? null };
      else if (event === "error") throw new Error(String(data.error ?? "stream error")); onEvent(event, data);
    }
    if (eof) break;
  }
  if (!done) throw new Error("Stream ended without a reply."); return done;
}

export const getConversations = () => request<Conversation[]>(`/users/${USER_ID}/conversations`);
export const getChatMessages = (conversationId: number) => request<ChatMessage[]>(`/conversations/${conversationId}/messages`);
export const deleteConversation = (conversationId: number) => request<{ deleted: boolean }>(`/conversations/${conversationId}`, { method: "DELETE" });
export const pinConversation = (conversationId: number, module_id: number | null) => request<{ id: number; module_id: number | null; module_name: string | null }>(`/conversations/${conversationId}/pin`, { method: "PATCH", body: JSON.stringify({ module_id }) });
export const renameConversation = (conversationId: number, title: string) => request<Conversation>(`/conversations/${conversationId}`, { method: "PATCH", body: JSON.stringify({ title }) });
export const getMemories = () => request<TutorMemory[]>(`/users/${USER_ID}/memories`);
export const deleteMemory = (memoryId: number) => request<{ deleted: boolean }>(`/memories/${memoryId}`, { method: "DELETE" });
