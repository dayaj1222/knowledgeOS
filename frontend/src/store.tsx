// Global data store — single source of truth for all shared entities.
//
// Courses, the selected course, its module/topic/resource tree, and
// proficiency are GLOBAL state. Every component reads from here via hooks;
// mutations go through actions that update the store once, so nothing goes
// stale or independently re-fetches. No external state library — plain React
// Context + hooks.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  getCourses,
  getModules,
  getTopics,
  getResources,
  getProficiency,
  createCourse,
  createModule,
  createTopic,
  deleteTopic,
  uploadResource,
  uploadSyllabus,
  pollResourceStatus,
  USER_ID,
} from "./api";
import type { Course, Module, Topic, Resource, Proficiency } from "./api";
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
  allCourseTrees: Record<number, { moduleId: number; moduleName: string; topics: Topic[] }[]>;
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
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [topicsByModule, setTopicsByModule] = useState<Record<number, Topic[]>>({});
  const [resources, setResources] = useState<Resource[]>([]);
  const [proficiency, setProficiency] = useState<Proficiency[]>([]);
  const [allCourseTrees, setAllCourseTrees] = useState<Record<number, { moduleId: number; moduleName: string; topics: Topic[] }[]>>({});
  const [loadingTree, setLoadingTree] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Global tutor thread: the bubble drawer and the /tutor page share it, so
  // moving between tabs continues the same conversation. Persisted so a
  // refresh doesn't lose the thread.
  const [activeConversationId, setActiveConversationIdState] = useState<number | null>(() => {
    const raw = localStorage.getItem("kb.activeConvo");
    const n = raw == null ? NaN : Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
  });
  const setActiveConversationId = useCallback((id: number | null) => {
    setActiveConversationIdState(id);
    if (id == null) localStorage.removeItem("kb.activeConvo");
    else localStorage.setItem("kb.activeConvo", String(id));
  }, []);

  // --- loaders ---

  const reloadCourses = useCallback(async () => {
    const data = await getCourses(USER_ID);
    setCourses(data);
  }, []);

  const reloadProficiency = useCallback(async () => {
    const data = await getProficiency(USER_ID);
    setProficiency(data);
  }, []);

  const loadAllTrees = useCallback(async () => {
    const courseList = await getCourses(USER_ID);
    const trees: Record<number, { moduleId: number; moduleName: string; topics: Topic[] }[]> = {};
    await Promise.all(courseList.map(async (c) => {
      const mods = await getModules(c.id);
      const entries = await Promise.all(mods.map(async (m) => ({
        moduleId: m.id,
        moduleName: m.name,
        topics: await getTopics(m.id),
      })));
      trees[c.id] = entries;
    }));
    setAllCourseTrees(trees);
  }, []);

  const reloadTree = useCallback(async (courseId: number) => {
    setLoadingTree(true);
    setError(null);
    try {
      const mods = await getModules(courseId);
      const topicsMap: Record<number, Topic[]> = {};
      await Promise.all(
        mods.map(async (m) => {
          topicsMap[m.id] = await getTopics(m.id);
        })
      );
      const res = await getResources(courseId);
      setModules(mods);
      setTopicsByModule(topicsMap);
      setResources(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingTree(false);
    }
  }, []);

  // Initial load + when selection changes
  useEffect(() => {
    reloadCourses();
    reloadProficiency();
    loadAllTrees();
  }, [reloadCourses, reloadProficiency, loadAllTrees]);

  useEffect(() => {
    if (selectedCourseId != null) {
      reloadTree(selectedCourseId);
    } else {
      setModules([]);
      setTopicsByModule({});
      setResources([]);
    }
  }, [selectedCourseId, reloadTree]);

  // --- actions ---

  const selectCourse = useCallback((id: number | null) => setSelectedCourseId(id), []);

  const addCourse = useCallback(async (name: string, code: string) => {
    try {
      await createCourse({ name, code });
      await reloadCourses();
    } catch (e) { notifyError(`Add course failed: ${(e as Error).message}`); throw e; }
  }, [reloadCourses]);

  const addModule = useCallback(async (courseId: number, name: string) => {
    try {
      await createModule(courseId, { name });
      await reloadTree(courseId);
    } catch (e) { notifyError(`Add module failed: ${(e as Error).message}`); throw e; }
  }, [reloadTree]);

  const addTopic = useCallback(async (moduleId: number, name: string) => {
    try {
      await createTopic({ module_id: moduleId, name });
      if (selectedCourseId != null) await reloadTree(selectedCourseId);
    } catch (e) { notifyError(`Add topic failed: ${(e as Error).message}`); throw e; }
  }, [reloadTree, selectedCourseId]);

  const removeTopic = useCallback(async (topicId: number) => {
    try {
      await deleteTopic(topicId);
      if (selectedCourseId != null) await reloadTree(selectedCourseId);
    } catch (e) { notifyError(`Delete topic failed: ${(e as Error).message}`); throw e; }
  }, [reloadTree, selectedCourseId]);

  const uploadSyllabusFile = useCallback(async (courseId: number, file: File) => {
    try {
      await uploadSyllabus(courseId, file);
      await reloadTree(courseId);
      await reloadCourses();
    } catch (e) { notifyError(`Syllabus upload failed: ${(e as Error).message}`); throw e; }
  }, [reloadTree, reloadCourses]);

  const uploadMaterialFile = useCallback(async (
    courseId: number, file: File, name: string, type: string, moduleId: number | null,
  ) => {
    const { resource_id } = await uploadResource(courseId, file, name, type, moduleId ?? undefined);
    // poll status until terminal, mirroring backend state (cap ~3 min: later
    // files in a batch wait behind earlier extractions in the server queue)
    for (let i = 0; i < 180; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const s = await pollResourceStatus(resource_id);
      if (s.terminal) {
        await reloadTree(courseId);
        return s;
      }
    }
    throw new Error("Timed out waiting for extraction");
  }, [reloadTree]);

  const uploadMaterialFiles = useCallback(async (
    courseId: number,
    files: { file: File; name: string; type: string; moduleId: number | null }[],
    onFileDone?: (index: number, status: ResourceStatusInfo) => void,
    onFileError?: (index: number, error: Error) => void,
  ) => {
    // Strictly sequential: the backend extracts one file at a time (same
    // pipeline as a single upload), so parallel uploads only contend on CPU
    // and SQLite and fail to parse. One failure never aborts the rest.
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
  }, [uploadMaterialFile, reloadTree]);

  const value = useMemo(() => ({
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
  }), [
    courses, selectedCourseId, modules, topicsByModule, resources, proficiency,
    allCourseTrees, loadingTree, error, activeConversationId, selectCourse,
    setActiveConversationId, reloadCourses, reloadTree,
    addCourse, addModule, addTopic, removeTopic, uploadSyllabusFile, uploadMaterialFile,
    uploadMaterialFiles,
  ]);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  return useContext(StoreContext);
}

export function useSelectedCourse(): Course | null {
  const { courses, selectedCourseId } = useStore();
  return courses.find((c) => c.id === selectedCourseId) ?? null;
}
