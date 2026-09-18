import { request, USER_ID } from "./core/client";
import type { Course, Module, Topic, Proficiency, EngineStatus, StudyLog } from "./core/types";

export type { Course, Module, Topic, Proficiency, StudyLog } from "./core/types";

export const getEngineStatus = () => request<EngineStatus>(`/status`);
export const clearConversations = (userId = USER_ID) => request<{ deleted: number }>(`/users/${userId}/conversations`, { method: "DELETE" });
export const getStudyLogs = (userId = USER_ID) => request<StudyLog[]>(`/users/${userId}/study-logs`);
export const getCourses = (userId = USER_ID) => request<Course[]>(`/users/${userId}/courses?include_counts=true`);
export const createCourse = (body: Partial<Course> & { name: string; code: string }) => request<Course>(`/users/${USER_ID}/courses`, { method: "POST", body: JSON.stringify(body) });
export const updateCourse = (courseId: number, body: Partial<Course>) => request<Course>(`/courses/${courseId}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteCourse = (courseId: number) => request<void>(`/courses/${courseId}`, { method: "DELETE" });
export const getModules = (courseId: number) => request<Module[]>(`/courses/${courseId}/modules`);
export const createModule = (courseId: number, body: { name: string }) => request<Module>(`/courses/${courseId}/modules`, { method: "POST", body: JSON.stringify(body) });
export const updateModule = (moduleId: number, body: Partial<Module>) => request<Module>(`/modules/${moduleId}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteModule = (moduleId: number) => request<void>(`/modules/${moduleId}`, { method: "DELETE" });
export const getTopics = (moduleId: number) => request<Topic[]>(`/modules/${moduleId}/topics`);
export const createTopic = (body: { module_id: number; name: string; description?: string; priority?: number; prerequisite_ids?: number[] }) => request<Topic>(`/topics`, { method: "POST", body: JSON.stringify(body) });
export const updateTopic = (topicId: number, body: Partial<Topic>) => request<Topic>(`/topics/${topicId}`, { method: "PATCH", body: JSON.stringify(body) });
export const deleteTopic = (topicId: number, force = false) => request<void>(`/topics/${topicId}${force ? "?force=true" : ""}`, { method: "DELETE" });
export const getProficiency = (userId = USER_ID) => request<Proficiency[]>(`/users/${userId}/proficiency`);
export const upsertProficiency = (topicId: number, body: Partial<Proficiency>) => request<Proficiency>(`/users/${USER_ID}/proficiency/${topicId}`, { method: "PUT", body: JSON.stringify(body) });
