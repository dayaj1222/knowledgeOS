import { request, USER_ID } from "./core/client";
import type { Assessment, Attempt, Deadline, Plan, Preference, Question, StudyLog } from "./core/types";
import type { ChatTurn } from "./chat";
export type { Assessment, Attempt, Deadline, Plan, Preference, Question } from "./core/types";

export const getQuestions = (topicId: number) => request<Question[]>(`/topics/${topicId}/questions`);
export const generateQuiz = (topicIds: number[], questionsPerTopic = 3, difficulty = "medium", instructions = "") => request<Question[]>(`/quiz/generate`, { method: "POST", body: JSON.stringify({ topic_ids: topicIds, questions_per_topic: questionsPerTopic, difficulty, instructions }) });
export const createQuestion = (topicId: number, body: { text: string; type: string; expected_key_points?: unknown[] }) => request<Question>(`/topics/${topicId}/questions`, { method: "POST", body: JSON.stringify({ topic_id: topicId, ...body }) });
export const createAssessment = (userId = USER_ID) => request<Assessment>(`/assessments`, { method: "POST", body: JSON.stringify({ user_id: userId }) });
export const getAssessment = (assessmentId: number) => request<Assessment & { questions: Question[] }>(`/assessments/${assessmentId}`);
export const patchAssessment = (assessmentId: number, status: string) => request<Assessment>(`/assessments/${assessmentId}`, { method: "PATCH", body: JSON.stringify({ status }) });
export const deleteAssessment = (assessmentId: number) => request<{ deleted: boolean }>(`/assessments/${assessmentId}`, { method: "DELETE" });
export const createAttempt = (body: { user_id: number; assessment_id: number; question_id: number; user_answer?: string }) => request<Attempt>(`/attempts`, { method: "POST", body: JSON.stringify(body) });
export const gradeAttempt = (attemptId: number, body: { score?: number; feedback?: string; status?: string; excluded?: boolean; user_answer?: string }) => request<Attempt>(`/attempts/${attemptId}/grade`, { method: "PATCH", body: JSON.stringify(body) });
export const submitChatQuiz = (conversationId: number, assessmentId: number) => request<ChatTurn>(`/chat/quiz/submit`, { method: "POST", body: JSON.stringify({ user_id: USER_ID, conversation_id: conversationId, assessment_id: assessmentId }) });

export const getPlans = (userId = USER_ID) => request<Plan[]>(`/users/${userId}/plans`);
export const getDeadlines = (userId = USER_ID) => request<Deadline[]>(`/users/${userId}/deadlines`);
export const createDeadline = (body: { user_id: number; course_id: number; title: string; due_date: string; weight?: number; topic_id?: number }) => request<Deadline>(`/deadlines`, { method: "POST", body: JSON.stringify(body) });
export const createStudyLog = (body: { topic_id: number; minutes_spent: number; confidence_after?: number; resource_id?: number }) => request<StudyLog>(`/study-logs`, { method: "POST", body: JSON.stringify({ user_id: USER_ID, ...body }) });
export const getPreference = (userId = USER_ID) => request<Preference>(`/users/${userId}/preference`);
export const putPreference = (body: Partial<Preference>) => request<Preference>(`/users/${USER_ID}/preference`, { method: "PUT", body: JSON.stringify(body) });
export const getSystemPrompt = (userId = USER_ID) => request<{ system_prompt: string }>(`/users/${userId}/system-prompt`);

export interface DueReview { topic_id: number; topic_name: string; due_date: string; interval_days: number; ease_factor: number; overdue_days: number }
export const getDueReviews = (userId = USER_ID, limit = 20) => request<DueReview[]>(`/users/${userId}/reviews/due?limit=${limit}`);
export const submitReviewResult = (body: { user_id: number; topic_id: number; quality: number }) => request(`/reviews/result`, { method: "POST", body: JSON.stringify(body) });
export const finishReviewSession = (conversationId: number, cardId: number) => request<{ finished: boolean }>(`/reviews/session/finish`, { method: "POST", body: JSON.stringify({ conversation_id: conversationId, card_id: cardId }) });
export interface TopicWeakness { topic_id: number; topic_name: string; score: number; total_missed: number; missed: { point: string; count: number }[] }
export const getWeaknesses = (userId = USER_ID) => request<TopicWeakness[]>(`/users/${userId}/weaknesses`);
export const generateDrill = (body: { user_id: number; topic_id?: number; count?: number; difficulty?: string }) => request<Question[]>(`/quiz/drill`, { method: "POST", body: JSON.stringify(body) });
