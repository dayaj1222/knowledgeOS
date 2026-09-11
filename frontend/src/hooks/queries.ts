// Server-state hooks — the single front door to backend data.
// Replaces hand-rolled fetch + localStorage caches (store.tsx, useChatThread).
// Thread/message queries keep localStorage as instant initialData + persist.

import { useQuery } from "@tanstack/react-query";
import {
  USER_ID,
  getChatMessages,
  getConversations,
  getCourses,
  getModules,
  getProficiency,
  getResources,
  getTopics,
  type ChatMessage,
  type Conversation,
  type Course,
  type Module,
  type Proficiency,
  type Resource,
  type Topic,
} from "../api";

function readLS<T>(key: string): T | undefined {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : undefined;
  } catch {
    return undefined;
  }
}

export function writeLS(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota/private mode — caching is best-effort.
  }
}

export const LS_CONVOS = "kb.convos";
export const LS_MSGS = (id: number) => `kb.chat.${id}`;

export interface CourseTree {
  modules: Module[];
  topicsByModule: Record<number, Topic[]>;
  resources: Resource[];
}

export function useCourses() {
  return useQuery({
    queryKey: ["courses", USER_ID],
    queryFn: () => getCourses(USER_ID),
  });
}

export function useProficiency() {
  return useQuery({
    queryKey: ["proficiency", USER_ID],
    queryFn: () => getProficiency(USER_ID),
  });
}

export function useCourseTree(courseId: number | null) {
  return useQuery({
    queryKey: ["tree", courseId],
    enabled: courseId != null,
    queryFn: async (): Promise<CourseTree> => {
      const mods = await getModules(courseId as number);
      const topicsByModule: Record<number, Topic[]> = {};
      await Promise.all(
        mods.map(async (m) => {
          topicsByModule[m.id] = await getTopics(m.id);
        })
      );
      const resources = await getResources(courseId as number);
      return { modules: mods, topicsByModule, resources };
    },
  });
}

export interface CourseTreeEntry {
  moduleId: number;
  moduleName: string;
  topics: Topic[];
}

export function useAllCourseTrees(courses: Course[] | undefined) {
  return useQuery({
    queryKey: ["all-trees", (courses ?? []).map((c) => c.id).join(",")],
    enabled: !!courses && courses.length > 0,
    queryFn: async (): Promise<Record<number, CourseTreeEntry[]>> => {
      const trees: Record<number, CourseTreeEntry[]> = {};
      await Promise.all(
        (courses ?? []).map(async (c) => {
          const mods = await getModules(c.id);
          trees[c.id] = await Promise.all(
            mods.map(async (m) => ({
              moduleId: m.id,
              moduleName: m.name,
              topics: await getTopics(m.id),
            }))
          );
        })
      );
      return trees;
    },
  });
}

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: getConversations,
    initialData: () => readLS<Conversation[]>(LS_CONVOS),
  });
}

export function useThreadMessages(conversationId: number | null) {
  return useQuery({
    queryKey: ["thread", conversationId],
    enabled: conversationId != null,
    queryFn: async (): Promise<ChatMessage[]> => {
      const fresh = await getChatMessages(conversationId as number);
      writeLS(LS_MSGS(conversationId as number), fresh);
      return fresh;
    },
    initialData: () =>
      conversationId == null ? [] : readLS<ChatMessage[]>(LS_MSGS(conversationId)),
  });
}

export type { Proficiency };
