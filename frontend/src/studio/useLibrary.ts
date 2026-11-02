import { useCallback, useEffect, useRef, useState } from "react";

import { createProject, deleteProject, getProject, listProjects, updateProject } from "./api";
import type { ProjectSummary } from "./types";

/** Shared by the sidebar counts, Home and Your videos; AI edits arrive on refresh. */
export function useLibrary() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [revision, setRevision] = useState(0);
  const mutation = useRef(0);
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let live = true;
    const version = mutation.current;
    listProjects().then(
      (list) => {
        if (!live || version !== mutation.current) return;
        setProjects(list);
        setError(null);
      },
      (problem) => { if (live) setError(problem); },
    );
    return () => { live = false; };
  }, [revision]);
  useEffect(() => {
    const refresh = () => { if (!document.hidden) retry(); };
    const timer = setInterval(refresh, 5000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [retry]);

  const remove = async (id: string) => {
    mutation.current += 1;
    await deleteProject(id);
    mutation.current += 1;
    setProjects((list) => (list ?? []).filter((project) => project.id !== id));
    retry();
  };
  const rename = async (id: string, title: string) => {
    mutation.current += 1;
    const saved = await updateProject(id, { title });
    mutation.current += 1;
    setProjects((list) => (list ?? []).map((project) => project.id === id ? { ...project, title: saved.title, updated: saved.updated } : project));
    retry();
  };
  const duplicate = async (id: string) => {
    mutation.current += 1;
    const source = await getProject(id);
    const copy = await createProject({ title: `${(source.title || "Untitled video").slice(0, 73)} (copy)`, template: source.template, params: source.params, settings: source.settings });
    mutation.current += 1;
    setProjects((list) => [copy, ...(list ?? []).filter((project) => project.id !== copy.id)]);
    retry();
    return copy;
  };
  return { projects, error, retry, revision, remove, rename, duplicate };
}

export type Library = ReturnType<typeof useLibrary>;
