// Shared executor for backend ui_actions (the tutor's hands on the UI).

import type { NavigateFunction } from "react-router-dom";
import type { UiAction } from "../api";
import { notifySuccess } from "./notifications";

const ALLOWED_ROUTES = new Set(["/", "/library", "/plan", "/settings"]);

export function runUiActions(
  actions: UiAction[],
  ctx: {
    navigate: NavigateFunction;
    selectCourse: (id: number) => void;
    reloadCourses: () => void;
    reloadTree: (courseId: number) => void;
    selectedCourseId: number | null;
  }
) {
  for (const a of actions ?? []) {
    const p = (a.params ?? {}) as Record<string, unknown>;
    try {
      if (
        a.action === "navigate" &&
        typeof p.route === "string" &&
        ALLOWED_ROUTES.has(p.route)
      ) {
        ctx.navigate(p.route);
      } else if (a.action === "select_course" && typeof p.course_id === "number") {
        ctx.selectCourse(p.course_id);
      } else if (a.action === "reload") {
        ctx.reloadCourses();
        if (ctx.selectedCourseId != null) ctx.reloadTree(ctx.selectedCourseId);
      } else if (a.action === "notify" && typeof p.message === "string") {
        notifySuccess(p.message);
      }
    } catch {
      // UI commands are best-effort; the chat reply already explains them.
    }
  }
}
