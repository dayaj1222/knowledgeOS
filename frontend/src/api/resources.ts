import { BASE_URL, USER_ID, request } from "./core/client";
import type { Passage, Resource } from "./core/types";
export type { Passage, Resource } from "./core/types";

export type ResourceStatus = "uploaded" | "processing" | "done" | "partial" | "failed";
export interface ResourceStatusInfo { status: ResourceStatus; error?: string | null; passage_count: number; terminal: boolean }
export interface PassageNote { id: number; passage_id: number; user_id: number; note: string; created_at?: string | null }

export const getResources = (courseId: number) => request<Resource[]>(`/courses/${courseId}/resources`);
export const getPassages = (resourceId: number) => request<Passage[]>(`/resources/${resourceId}/passages`);
export const getPassageNotes = (passageId: number) => request<PassageNote[]>(`/passages/${passageId}/notes`);
export const addPassageNote = (passageId: number, note: string) => request<PassageNote>(`/passages/${passageId}/notes`, { method: "POST", body: JSON.stringify({ user_id: USER_ID, note }) });
export const deletePassageNote = (noteId: number) => request<{ deleted: boolean }>(`/passages/notes/${noteId}`, { method: "DELETE" });

async function upload(file: File, url: string, fields: Record<string, string>, failureLabel = "Upload failed"): Promise<unknown> {
  const fd = new FormData();
  fd.append("file", file);
  for (const [key, value] of Object.entries(fields)) fd.append(key, value);
  const res = await fetch(`${BASE_URL}${url}`, { method: "POST", body: fd });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as { error?: { detail?: unknown } }).error?.detail;
    throw new Error(detail ? String(detail) : `${failureLabel} (${res.status})`);
  }
  return (body as { data: unknown }).data;
}

export async function uploadResource(courseId: number, file: File, name?: string, type = "pdf", moduleId?: number): Promise<{ resource_id: number; status: string }> {
  const fields: Record<string, string> = { type };
  if (name) fields.name = name;
  if (moduleId != null) fields.module_id = String(moduleId);
  return (await upload(file, `/courses/${courseId}/resources`, fields)) as { resource_id: number; status: string };
}

export async function uploadSyllabus(courseId: number, file: File): Promise<{ modules: { module_id: number; module: string; topics: { topic_id: number; name: string }[] }[] }> {
  const result = await upload(file, `/courses/${courseId}/syllabus`, {}, "Syllabus upload failed");
  return result as { modules: { module_id: number; module: string; topics: { topic_id: number; name: string }[] }[] };
}

export const pollResourceStatus = (resourceId: number) => request<ResourceStatusInfo>(`/resources/${resourceId}/status`);
