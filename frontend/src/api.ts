const BASE_URL = "http://localhost:8000/api";
export const USER_ID = 1;

// Every backend response uses the standard envelope:
//   { data: <payload>, meta: { request_id }, error: null }
// Errors: { data: null, meta, error: { type, detail } }
interface Envelope<T> {
  data: T;
  meta: { request_id: string };
  error: { type: string; detail: unknown } | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = (await res.json().catch(() => ({}))) as Partial<Envelope<T>> | T;
  if (!res.ok) {
    const detail = (body as Partial<Envelope<T>>).error?.detail;
    throw new Error(detail ? String(detail) : `API ${res.status}: ${res.statusText}`);
  }
  // Tolerate a stale backend serving raw JSON (no envelope) instead of
  // crashing every screen on `undefined.map`.
  if (body !== null && typeof body === "object" && "data" in (body as object)) {
    const env = body as Partial<Envelope<T>>;
    if (env.error) {
      const detail = env.error?.detail;
      throw new Error(detail ? String(detail) : `API ${res.status}: ${res.statusText}`);
    }
    return env.data as T;
  }
  return body as T;
}

// ---- Types ----
export interface Course {
  id: number;
  user_id: number;
  name: string;
  code: string;
  type: string;
  instructor?: string | null;
  credits: number;
  status: string;
  color?: string | null;
  module_count?: number;
  topic_count?: number;
}

export interface Module {
  id: number;
  course_id: number;
  name: string;
  order_index: number;
  topic_count?: number;
}

export interface Topic {
  id: number;
  module_id: number;
  parent_topic_id?: number | null;
  name: string;
  description?: string | null;
  order_index: number;
  priority: number;
  prerequisite_ids: number[];
  passage_count?: number;
}

export interface Proficiency {
  user_id: number;
  topic_id: number;
  score: number;
  weak_points: unknown[];
  strengths: unknown[];
  preferred_method: string;
}

export interface Resource {
  id: number;
  user_id: number;
  course_id: number;
  name: string;
  type: string;
  file_path: string;
  status?: string;
  error?: string | null;
  module_id?: number | null;
  topic_id?: number | null;
}

export interface Passage {
  id: number;
  resource_id: number;
  content: string;
  index_order: number;
  page_start?: number;
  page_end?: number;
  topic_id?: number | null;
}

export interface Question {
  id: number;
  topic_id: number;
  text: string;
  type: string;
  expected_key_points: unknown[];
  images?: string | null;
}

export interface Assessment {
  id: number;
  user_id: number;
  status: string;
}

export interface Attempt {
  id: number;
  user_id: number;
  assessment_id: number;
  question_id: number;
  user_answer?: string | null;
  score: number;
  feedback?: string | null;
  matched_key_points: string[];
  missed_key_points: string[];
  status: string;
  excluded: boolean;
}

export interface Deadline {
  id: number;
  user_id: number;
  course_id: number;
  topic_id?: number | null;
  title: string;
  due_date: string;
  weight: number;
}

export interface Plan {
  id: number;
  user_id: number;
  slot_id?: number | null;
  topic_id: number;
  suggested_duration_minutes: number;
  status: string;
  generated_at: string;
}

export interface Preference {
  user_id: number;
  session_length_minutes: number;
  daily_goal_minutes: number;
  preferred_start?: string | null;
  preferred_end?: string | null;
  tutor_instructions?: string | null;
}

export interface StudyLog {
  id: number;
  user_id: number;
  topic_id: number;
  resource_id?: number | null;
  passage_id?: number | null;
  plan_id?: number | null;
  minutes_spent: number;
  confidence_after?: number | null;
}

// ---- Courses ----
export const getCourses = (userId = USER_ID) =>
  request<Course[]>(`/users/${userId}/courses?include_counts=true`);
export const createCourse = (body: Partial<Course> & { name: string; code: string }) =>
  request<Course>(`/users/${USER_ID}/courses`, { method: "POST", body: JSON.stringify(body) });
export const updateCourse = (courseId: number, body: Partial<Course>) =>
  request<Course>(`/courses/${courseId}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteCourse = (courseId: number) =>
  request<void>(`/courses/${courseId}`, { method: "DELETE" });

// ---- Modules ----
export const getModules = (courseId: number) =>
  request<Module[]>(`/courses/${courseId}/modules`);
export const createModule = (courseId: number, body: { name: string }) =>
  request<Module>(`/courses/${courseId}/modules`, { method: "POST", body: JSON.stringify(body) });
export const updateModule = (moduleId: number, body: Partial<Module>) =>
  request<Module>(`/modules/${moduleId}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteModule = (moduleId: number) =>
  request<void>(`/modules/${moduleId}`, { method: "DELETE" });

// ---- Topics ----
export const getTopics = (moduleId: number) =>
  request<Topic[]>(`/modules/${moduleId}/topics`);
export const createTopic = (body: { module_id: number; name: string; description?: string; priority?: number; prerequisite_ids?: number[] }) =>
  request<Topic>(`/topics`, { method: "POST", body: JSON.stringify(body) });
export const updateTopic = (topicId: number, body: Partial<Topic>) =>
  request<Topic>(`/topics/${topicId}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteTopic = (topicId: number, force = false) =>
  request<void>(`/topics/${topicId}${force ? "?force=true" : ""}`, { method: "DELETE" });

// ---- Proficiency ----
export const getProficiency = (userId = USER_ID) =>
  request<Proficiency[]>(`/users/${userId}/proficiency`);
export const upsertProficiency = (topicId: number, body: Partial<Proficiency>) =>
  request<Proficiency>(`/users/${USER_ID}/proficiency/${topicId}`, { method: "PUT", body: JSON.stringify(body) });

// ---- Resources (upload + passages + async status) ----
// Upload is multipart, so it can't use the JSON helper above — but it
// unwraps the same envelope.

export type ResourceStatus =
  | "uploaded" | "processing" | "done" | "partial" | "failed";

export interface ResourceStatusInfo {
  status: ResourceStatus;
  error?: string | null;
  passage_count: number;
  terminal: boolean;
}

export const getResources = (courseId: number) =>
  request<Resource[]>(`/courses/${courseId}/resources`);

export const getPassages = (resourceId: number) =>
  request<Passage[]>(`/resources/${resourceId}/passages`);

// ---- Passage notes (tutor + learner annotations) ----
export interface PassageNote {
  id: number;
  passage_id: number;
  user_id: number;
  note: string;
  created_at?: string | null;
}

export const getPassageNotes = (passageId: number) =>
  request<PassageNote[]>(`/passages/${passageId}/notes`);

export const addPassageNote = (passageId: number, note: string) =>
  request<PassageNote>(`/passages/${passageId}/notes`, {
    method: "POST",
    body: JSON.stringify({ user_id: USER_ID, note }),
  });

export const deletePassageNote = (noteId: number) =>
  request<{ deleted: boolean }>(`/passages/notes/${noteId}`, { method: "DELETE" });

// Upload is multipart, so it can't use the JSON helpers above.
export async function uploadResource(
  courseId: number,
  file: File,
  name?: string,
  type = "pdf",
  moduleId?: number,
): Promise<{ resource_id: number; status: string }> {
  const fd = new FormData();
  fd.append("file", file);
  if (name) fd.append("name", name);
  fd.append("type", type);
  if (moduleId != null) fd.append("module_id", String(moduleId));
  const res = await fetch(`${BASE_URL}/courses/${courseId}/resources`, {
    method: "POST",
    body: fd,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { error?: { detail?: unknown } }).error?.detail;
    throw new Error(detail ? String(detail) : `Upload failed (${res.status})`);
  }
  return (body as { data: { resource_id: number; status: string } }).data;
}

// Syllabus upload: the LLM parses the syllabus and creates modules+topics.
export async function uploadSyllabus(
  courseId: number,
  file: File,
): Promise<{ modules: { module_id: number; module: string; topics: { topic_id: number; name: string }[] }[] }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE_URL}/courses/${courseId}/syllabus`, {
    method: "POST",
    body: fd,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { error?: { detail?: unknown } }).error?.detail;
    throw new Error(detail ? String(detail) : `Syllabus upload failed (${res.status})`);
  }
  return (body as { data: { modules: unknown[] } }).data as any;
}

export const pollResourceStatus = (resourceId: number) =>
  request<ResourceStatusInfo>(`/resources/${resourceId}/status`);

// ---- Questions / Quiz ----
export const getQuestions = (topicId: number) =>
  request<Question[]>(`/topics/${topicId}/questions`);
export const generateQuiz = (topicIds: number[], questionsPerTopic = 3, difficulty = "medium", instructions = "") =>
  request<Question[]>(`/quiz/generate`, { method: "POST", body: JSON.stringify({ topic_ids: topicIds, questions_per_topic: questionsPerTopic, difficulty, instructions }) });
export const createQuestion = (topicId: number, body: { text: string; type: string; expected_key_points?: unknown[] }) =>
  request<Question>(`/topics/${topicId}/questions`, { method: "POST", body: JSON.stringify({ topic_id: topicId, ...body }) });
export const createAssessment = (userId = USER_ID) =>
  request<Assessment>(`/assessments`, { method: "POST", body: JSON.stringify({ user_id: userId }) });
export const getAssessment = (assessmentId: number) =>
  request<Assessment & { questions: Question[] }>(`/assessments/${assessmentId}`);
export const patchAssessment = (assessmentId: number, status: string) =>
  request<Assessment>(`/assessments/${assessmentId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
export const deleteAssessment = (assessmentId: number) =>
  request<{ deleted: boolean }>(`/assessments/${assessmentId}`, { method: "DELETE" });
export const createAttempt = (body: { user_id: number; assessment_id: number; question_id: number; user_answer?: string }) =>
  request<Attempt>(`/attempts`, { method: "POST", body: JSON.stringify(body) });
export const gradeAttempt = (attemptId: number, body: { score?: number; feedback?: string; status?: string; excluded?: boolean; user_answer?: string }) =>
  request<Attempt>(`/attempts/${attemptId}/grade`, { method: "PATCH", body: JSON.stringify(body) });

// ---- In-chat quiz: per-card answers are graded silently via createAttempt +
// gradeAttempt above; finishing runs the hidden tutor debrief and returns
// ONLY the recommendation as a normal chat turn.
export const submitChatQuiz = (conversationId: number, assessmentId: number) =>
  request<ChatTurn>(`/chat/quiz/submit`, {
    method: "POST",
    body: JSON.stringify({ user_id: USER_ID, conversation_id: conversationId, assessment_id: assessmentId }),
  });

// ---- Plans / Study logs / Deadlines ----
export const getPlans = (userId = USER_ID) =>
  request<Plan[]>(`/users/${userId}/plans`);
export const getDeadlines = (userId = USER_ID) =>
  request<Deadline[]>(`/users/${userId}/deadlines`);
export const createDeadline = (body: { user_id: number; course_id: number; title: string; due_date: string; weight?: number; topic_id?: number }) =>
  request<Deadline>(`/deadlines`, { method: "POST", body: JSON.stringify(body) });
export const createStudyLog = (body: { topic_id: number; minutes_spent: number; confidence_after?: number; resource_id?: number }) =>
  request<StudyLog>(`/study-logs`, { method: "POST", body: JSON.stringify({ user_id: USER_ID, ...body }) });

// ---- Preference ----
export const getPreference = (userId = USER_ID) =>
  request<Preference>(`/users/${userId}/preference`);
export const putPreference = (body: Partial<Preference>) =>
  request<Preference>(`/users/${USER_ID}/preference`, { method: "PUT", body: JSON.stringify(body) });

// ---- Spaced repetition ----
export interface DueReview {
  topic_id: number;
  topic_name: string;
  due_date: string;
  interval_days: number;
  ease_factor: number;
  overdue_days: number;
}

export const getDueReviews = (userId = USER_ID, limit = 20) =>
  request<DueReview[]>(`/users/${userId}/reviews/due?limit=${limit}`);
export const submitReviewResult = (body: { user_id: number; topic_id: number; quality: number }) =>
  request(`/reviews/result`, { method: "POST", body: JSON.stringify(body) });

// ---- Weakness diagnosis + targeted drills ----
export interface TopicWeakness {
  topic_id: number;
  topic_name: string;
  score: number;
  total_missed: number;
  missed: { point: string; count: number }[];
}

export const getWeaknesses = (userId = USER_ID) =>
  request<TopicWeakness[]>(`/users/${userId}/weaknesses`);
export const generateDrill = (body: { user_id: number; topic_id?: number; count?: number; difficulty?: string }) =>
  request<Question[]>(`/quiz/drill`, { method: "POST", body: JSON.stringify(body) });

// ---- Tutor chat ----
export interface UiAction {
  action: string;
  params: Record<string, unknown>;
}

export interface ToolCall {
  tool: string;
  args: unknown;
  result_preview?: string | null;
}

export interface ChatTurn {
  conversation_id: number;
  reply: string;
  tool_calls: ToolCall[];
  ui_actions: UiAction[];
  quiz?: InlineQuizPayload | null;
  clarify?: InlineClarifyPayload | null;
}

export interface QuizQuestion {
  id: number;
  topic_id: number;
  text: string;
  type: string;
  expected_key_points?: unknown[];
}

export interface InlineQuizPayload {
  message_id: number;
  assessment_id: number;
  questions: QuizQuestion[];
}

export interface InlineClarifyPayload {
  message_id: number;
  question: string;
  options: string[];
  allow_free_text: boolean;
  completed?: boolean;
  answer?: string | null;
}

export interface Conversation {
  id: number;
  title: string;
}

export interface ChatMessage {
  id: number;
  role: string;
  content: string;
  tool_calls?: ToolCall[] | null;
  created_at?: string | null;
}

export interface UiContext {
  route: string;
  course_id?: number | null;
  course_name?: string | null;
  detail?: string | null;
}

export const sendChat = (
  message: string,
  conversationId?: number | null,
  uiContext?: UiContext | null,
) =>
  request<ChatTurn>(`/chat`, {
    method: "POST",
    body: JSON.stringify({
      user_id: USER_ID,
      conversation_id: conversationId ?? null,
      message,
      ui_context: uiContext ?? null,
    }),
  });

// Streaming twin: POSTs an SSE request, invoking onEvent for each frame.
// Resolves with the `done` payload (same shape as ChatTurn).
export async function sendChatStream(
  message: string,
  conversationId: number | null | undefined,
  onEvent: (type: string, data: Record<string, unknown>) => void,
  uiContext?: UiContext | null,
): Promise<ChatTurn> {
  const res = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: USER_ID,
      conversation_id: conversationId ?? null,
      message,
      ui_context: uiContext ?? null,
    }),
  });
  if (!res.ok || !res.body) throw new Error(`Chat stream failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let done: ChatTurn | null = null;
  for (;;) {
    const { value, done: eof } = await reader.read();
    if (value) buf += decoder.decode(value, { stream: true });
    buf = buf.replace(/\r\n/g, "\n"); // sse-starlette uses CRLF; normalize
    // Parse complete SSE frames (event: / data: pairs separated by blank line).
    for (;;) {
      const sep = buf.indexOf("\n\n");
      if (sep === -1) break;
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      const event = (/^event:\s*(.*)$/m.exec(frame) ?? [])[1]?.trim() ?? "message";
      const dataLines = frame
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim());
      if (!dataLines.length) continue;
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      } catch {
        continue;
      }
      if (event === "done") {
        done = {
          conversation_id: data.conversation_id as number,
          reply: data.reply as string,
          tool_calls: (data.tool_calls as ToolCall[]) ?? [],
          ui_actions: (data.ui_actions as UiAction[]) ?? [],
          quiz: (data.quiz as InlineQuizPayload | null) ?? null,
          clarify: (data.clarify as InlineClarifyPayload | null) ?? null,
        };
      } else if (event === "error") {
        throw new Error(String(data.error ?? "stream error"));
      }
      onEvent(event, data);
    }
    if (eof) break;
  }
  if (!done) throw new Error("Stream ended without a reply.");
  return done;
}

export const getConversations = () =>
  request<Conversation[]>(`/users/${USER_ID}/conversations`);

export const getChatMessages = (conversationId: number) =>
  request<ChatMessage[]>(`/conversations/${conversationId}/messages`);

export const deleteConversation = (conversationId: number) =>
  request<{ deleted: boolean }>(`/conversations/${conversationId}`, { method: "DELETE" });

export const renameConversation = (conversationId: number, title: string) =>
  request<Conversation>(`/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });

export interface TutorMemory {
  id: number;
  key: string;
  value: string;
}

export const getMemories = () =>
  request<TutorMemory[]>(`/users/${USER_ID}/memories`);

export const deleteMemory = (memoryId: number) =>
  request<{ deleted: boolean }>(`/memories/${memoryId}`, { method: "DELETE" });
