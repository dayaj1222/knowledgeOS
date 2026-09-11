// Global data store — UI state + React Query server state.
//
// UI state (selected course, active conversation) lives here in useState.
// Server state (courses, trees, proficiency) lives in React Query
// (src/hooks/queries.ts); this provider derives the legacy context shape
// from queries so screens migrate without rewrites. Mutations invalidate.

import { createContext, useCallback, useContext, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  createCourse,
  createModule,
  createTopic,
  deleteTopic,
  pollResourceStatus,
  uploadResource,
  uploadSyllabus,
  USER_ID,
} from "./api";
import type { Course, Module, Topic, Resource, Proficiency } from "./api";
import {
  useAllCourseTrees,
  useCourses,
  useCourseTree,
  useProficiency,
  type CourseTreeEntry,
} from "./hooks/queries";
import { notifyError } from "./components/notifications";

interface ResourceStatusInfo {
  status: string;
  error?: string | null;
  passage_count: number;
  terminal: boolean;
}

interface StoreState {
  courses: Course[];
  selectedCourseId: number | null;
  modules: Module[];
  topicsByModule: Record<number, Topic[]>;
  resources: Resource[];
  proficiency: Proficiency[];
  allCourseTrees: Record<number, CourseTreeEntry[]>;
  loadingTree: boolean;
  error: string | null;
  activeConversationId: number | null;
}

interface StoreActions {
  selectCourse: (id: number | null) => void;
  setActiveConversationId: (id: number | null) => void;
  reloadCourses: () => Promise<void>;
  reloadTree: (courseId: number) => Promise<void>;
  addCourse: (name: string, code: string) => Promise<void>;
  addModule: (courseId: number, name: string) => Promise<void>;
  addTopic: (moduleId: number, name: string) => Promise<void>;
  removeTopic: (topicId: number) => Promise<void>;
  uploadSyllabusFile: (courseId: number, file: File) => Promise<void>;
  uploadMaterialFile: (courseId: number, file: File, name: string, type: string, moduleId: number | null) => Promise<ResourceStatusInfo>;
  uploadMaterialFiles: (courseId: number, files: { file: File; name: string; type: string; moduleId: number | null }[], onFileDone?: (index: number, status: ResourceStatusInfo) => void, onFileError?: (index: number, error: Error) => void) => Promise<(ResourceStatusInfo | undefined)[]>;
}

const StoreContext = createContext<StoreState & StoreActions>(null as any);

export function DataProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [activeConversationId, setActiveConversationIdState] = useState<number | null>(() => {
    const raw = localStorage.getItem("kb.activeConvo");
    const n = raw == null ? NaN : Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
  });

  const coursesQuery = useCourses();
  const proficiencyQuery = useProficiency();
  const treeQuery = useCourseTree(selectedCourseId);
  const allTreesQuery = useAllCourseTrees(coursesQuery.data);

  const courses = coursesQuery.data ?? [];
  const proficiency = proficiencyQuery.data ?? [];
  const modules = treeQuery.data?.modules ?? [];
  const topicsByModule = treeQuery.data?.topicsByModule ?? {};
  const resources = treeQuery.data?.resources ?? [];
  const allCourseTrees = allTreesQuery.data ?? {};
  const loadingTree = treeQuery.isPending && selectedCourseId != null;
  const error =
    (treeQuery.error as Error | undefined)?.message ??
    (coursesQuery.error as Error | undefined)?.message ??
    null;

  const setActiveConversationId = useCallback((id: number | null) => {
    setActiveConversationIdState(id);
    if (id == null) localStorage.removeItem("kb.activeConvo");
    else localStorage.setItem("kb.activeConvo", String(id));
  }, []);

  const reloadCourses = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["courses", USER_ID] });
  }, [queryClient]);

  const reloadTree = useCallback(
    async (courseId: number) => {
      await queryClient.invalidateQueries({ queryKey: ["tree", courseId] });
    },
    [queryClient]
  );

  const selectCourse = useCallback((id: number | null) => setSelectedCourseId(id), []);

  const addCourse = useCallback(
    async (name: string, code: string) => {
      try {
        await createCourse({ name, code });
        await reloadCourses();
      } catch (e) {
        notifyError(`Add course failed: ${(e as Error).message}`);
        throw e;
      }
    },
    [reloadCourses]
  );

  const addModule = useCallback(
    async (courseId: number, name: string) => {
      try {
        await createModule(courseId, { name });
        await reloadTree(courseId);
      } catch (e) {
        notifyError(`Add module failed: ${(e as Error).message}`);
        throw e;
      }
    },
    [reloadTree]
  );

  const addTopic = useCallback(
    async (moduleId: number, name: string) => {
      try {
        await createTopic({ module_id: moduleId, name });
        if (selectedCourseId != null) await reloadTree(selectedCourseId);
      } catch (e) {
        notifyError(`Add topic failed: ${(e as Error).message}`);
        throw e;
      }
    },
    [reloadTree, selectedCourseId]
  );

  const removeTopic = useCallback(
    async (topicId: number) => {
      try {
        await deleteTopic(topicId);
        if (selectedCourseId != null) await reloadTree(selectedCourseId);
      } catch (e) {
        notifyError(`Delete topic failed: ${(e as Error).message}`);
        throw e;
      }
    },
    [reloadTree, selectedCourseId]
  );

  const uploadSyllabusFile = useCallback(
    async (courseId: number, file: File) => {
      try {
        await uploadSyllabus(courseId, file);
        await reloadTree(courseId);
        await reloadCourses();
      } catch (e) {
        notifyError(`Syllabus upload failed: ${(e as Error).message}`);
        throw e;
      }
    },
    [reloadTree, reloadCourses]
  );

  const uploadMaterialFile = useCallback(
    async (
      courseId: number,
      file: File,
      name: string,
      type: string,
      moduleId: number | null
    ) => {
      const { resource_id } = await uploadResource(courseId, file, name, type, moduleId ?? undefined);
      for (let i = 0; i < 180; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const s = await pollResourceStatus(resource_id);
        if (s.terminal) {
          await reloadTree(courseId);
          return s;
        }
      }
      throw new Error("Timed out waiting for extraction");
    },
    [reloadTree]
  );

  const uploadMaterialFiles = useCallback(
    async (
      courseId: number,
      files: { file: File; name: string; type: string; moduleId: number | null }[],
      onFileDone?: (index: number, status: ResourceStatusInfo) => void,
      onFileError?: (index: number, error: Error) => void
    ) => {
      const results: (ResourceStatusInfo | undefined)[] = new Array(files.length);
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        try {
          results[i] = await uploadMaterialFile(courseId, f.file, f.name, f.type, f.moduleId);
          onFileDone?.(i, results[i]!);
        } catch (e) {
          onFileError?.(i, e as Error);
        }
      }
      await reloadTree(courseId);
      return results;
    },
    [uploadMaterialFile, reloadTree]
  );

  const value: StoreState & StoreActions = {
    courses,
    selectedCourseId,
    modules,
    topicsByModule,
    resources,
    proficiency,
    allCourseTrees,
    loadingTree,
    error,
    activeConversationId,
    selectCourse,
    setActiveConversationId,
    reloadCourses,
    reloadTree,
    addCourse,
    addModule,
    addTopic,
    removeTopic,
    uploadSyllabusFile,
    uploadMaterialFile,
    uploadMaterialFiles,
  };

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  return useContext(StoreContext);
}

export function useSelectedCourse(): Course | null {
  const { courses, selectedCourseId } = useStore();
  return courses.find((c) => c.id === selectedCourseId) ?? null;
}
