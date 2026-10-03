import { useCallback, useEffect, useRef, useState } from "react";

import { deleteRequest, postJson, requestJson } from "@/lib/api";
import { ALLOWED_ASSET_EXTENSIONS, MAX_ASSET_SIZE_BYTES } from "@/lib/constants";
import { loadBrowserFiles, readStored, saveBrowserFiles, STORAGE_KEYS, writeStored } from "@/lib/storage";
import type { MediaFile, ParseResult, ScriptFile, StorageMode, WorkspaceFiles } from "@/lib/types";

const EMPTY_FILES: WorkspaceFiles = { scripts: [], assets: [], media: [] };
const EMPTY_PARSE: ParseResult = { scenes: [], animations: {} };
const PARSE_DEBOUNCE_MS = 400;

export type FilesStatus = "loading" | "ready" | "error";

interface FileContentResponse extends ParseResult {
  filename: string;
  code: string;
}

interface SaveResponse extends ParseResult {
  filename: string;
}

function browserScriptList(): ScriptFile[] {
  const encoder = new TextEncoder();
  return Object.entries(loadBrowserFiles())
    .map(([name, content]) => ({ name, size: encoder.encode(content).length, type: "script" as const }))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}

function parseCode(code: string): Promise<ParseResult | null> {
  return postJson<ParseResult>("/api/parse-code", { code }).catch(() => null);
}

function withoutKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  if (!(key in record)) return record;
  const copy = { ...record };
  delete copy[key];
  return copy;
}

function activeFileKey(mode: StorageMode) {
  return `${STORAGE_KEYS.activeFile}.${mode}`;
}

function fileKey(mode: StorageMode, file: string) {
  return `${mode}:${file}`;
}

/**
 * Scripts, assets, and renders plus the editor buffer for the open script.
 * Scripts live on the server ("disk") or in localStorage ("browser").
 *
 * Switching files never loses edits: an unsaved buffer is kept as an in-memory
 * draft and restored when its file is opened again, like an editor tab.
 */
export function useWorkspace({ mode, online }: { mode: StorageMode; online: boolean }) {
  const [files, setFiles] = useState<WorkspaceFiles>(EMPTY_FILES);
  const [filesStatus, setFilesStatus] = useState<FilesStatus>("loading");
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [savedCode, setSavedCode] = useState("");
  const [parsed, setParsed] = useState<ParseResult>(EMPTY_PARSE);
  const [selectedScene, setSelectedSceneState] = useState("");
  // "mode:file" -> unsaved contents of files that are not currently open.
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  // Latest values for async callbacks.
  const modeRef = useRef(mode);
  const activeFileRef = useRef<string | null>(null);
  const codeRef = useRef("");
  const savedCodeRef = useRef("");
  const draftsRef = useRef<Record<string, string>>({});
  const parsedRef = useRef<ParseResult>(EMPTY_PARSE);
  const parsedCodeRef = useRef<string | null>(null);
  const loadSeq = useRef(0);

  useEffect(() => {
    codeRef.current = code;
  }, [code]);

  const updateDrafts = useCallback((change: (drafts: Record<string, string>) => Record<string, string>) => {
    draftsRef.current = change(draftsRef.current);
    setDrafts(draftsRef.current);
  }, []);

  const applyParse = useCallback((result: ParseResult, file: string | null, source: string) => {
    parsedCodeRef.current = source;
    parsedRef.current = result;
    setParsed(result);
    const remembered = file
      ? readStored<Record<string, string>>(STORAGE_KEYS.sceneByFile, {})[fileKey(modeRef.current, file)]
      : undefined;
    setSelectedSceneState((previous) => {
      if (previous && result.scenes.includes(previous)) return previous;
      if (remembered && result.scenes.includes(remembered)) return remembered;
      return result.scenes[0] ?? "";
    });
  }, []);

  const setSelectedScene = useCallback((scene: string) => {
    setSelectedSceneState(scene);
    const file = activeFileRef.current;
    if (!file) return;
    const memory = readStored<Record<string, string>>(STORAGE_KEYS.sceneByFile, {});
    writeStored(STORAGE_KEYS.sceneByFile, { ...memory, [fileKey(modeRef.current, file)]: scene });
  }, []);

  const refreshFiles = useCallback(async (): Promise<WorkspaceFiles | null> => {
    let server: WorkspaceFiles | null = null;
    try {
      server = await requestJson<WorkspaceFiles>("/api/files");
    } catch {
      if (modeRef.current === "disk") {
        setFilesStatus("error");
        return null;
      }
    }
    const next =
      modeRef.current === "browser"
        ? { scripts: browserScriptList(), assets: server?.assets ?? [], media: server?.media ?? [] }
        : (server ?? EMPTY_FILES);
    setFiles(next);
    setFilesStatus("ready");
    return next;
  }, []);

  /** Show *file* with its saved *content*, restoring an unsaved draft of it if there is one. */
  const showBuffer = useCallback(
    (file: string | null, content: string) => {
      const previous = activeFileRef.current;
      if (previous && previous !== file && codeRef.current !== savedCodeRef.current) {
        const stash = codeRef.current;
        updateDrafts((all) => ({ ...all, [fileKey(modeRef.current, previous)]: stash }));
      }

      const key = file ? fileKey(modeRef.current, file) : null;
      const draft = key ? draftsRef.current[key] : undefined;
      if (key && draft !== undefined) {
        updateDrafts((all) => withoutKey(all, key));
      }
      const buffer = draft ?? content;

      activeFileRef.current = file;
      codeRef.current = buffer;
      savedCodeRef.current = content;
      setActiveFile(file);
      setCode(buffer);
      setSavedCode(content);
      if (file) writeStored(activeFileKey(modeRef.current), file);
    },
    [updateDrafts],
  );

  /** Load *name* into the editor (unsaved changes in the current buffer are dropped). */
  const openFile = useCallback(
    async (name: string): Promise<boolean> => {
      const seq = ++loadSeq.current;
      if (modeRef.current === "browser") {
        showBuffer(name, loadBrowserFiles()[name] ?? "");
        parsedCodeRef.current = null; // parsed by the debounced effect
        return true;
      }
      const data = await requestJson<FileContentResponse>(`/api/file-content?filename=${encodeURIComponent(name)}`);
      if (seq !== loadSeq.current) return false;
      showBuffer(data.filename, data.code);
      applyParse({ scenes: data.scenes, animations: data.animations }, data.filename, data.code);
      return true;
    },
    [applyParse, showBuffer],
  );

  const initialize = useCallback(async () => {
    const next = await refreshFiles();
    if (!next) return;
    const names = next.scripts.map((script) => script.name);
    const remembered = readStored<string | null>(activeFileKey(modeRef.current), null);
    const target = remembered && names.includes(remembered) ? remembered : names[0];
    if (target) {
      await openFile(target).catch(() => false);
    } else {
      showBuffer(null, "");
      applyParse(EMPTY_PARSE, null, "");
    }
  }, [applyParse, openFile, refreshFiles, showBuffer]);

  // (Re)load everything when the storage mode changes.
  useEffect(() => {
    const previousMode = modeRef.current;
    const previousFile = activeFileRef.current;
    if (previousMode !== mode && previousFile && codeRef.current !== savedCodeRef.current) {
      const stash = codeRef.current;
      updateDrafts((all) => ({ ...all, [fileKey(previousMode, previousFile)]: stash }));
    }
    modeRef.current = mode;
    activeFileRef.current = null;
    void initialize();
  }, [mode, initialize, updateDrafts]);

  // The server came back and nothing could be loaded before: try again.
  useEffect(() => {
    if (online && activeFileRef.current === null && modeRef.current === "disk") void initialize();
  }, [online, initialize]);

  // Keep the scene list and timeline in sync with the buffer while typing.
  useEffect(() => {
    if (code === parsedCodeRef.current) return;
    const source = code;
    const timer = setTimeout(async () => {
      const result = await parseCode(source);
      if (result && codeRef.current === source) applyParse(result, activeFileRef.current, source);
    }, PARSE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [code, applyParse]);

  /** Parse the current buffer now, skipping the debounce. */
  const parseNow = useCallback(async (): Promise<ParseResult | null> => {
    const source = codeRef.current;
    if (source === parsedCodeRef.current) return parsedRef.current;
    const result = await parseCode(source);
    if (result) applyParse(result, activeFileRef.current, source);
    return result;
  }, [applyParse]);

  /** Save the buffer. Resolves with the scenes it contains; throws on failure. */
  const save = useCallback(async (): Promise<ParseResult> => {
    const name = activeFileRef.current;
    if (!name) throw new Error("No file is open.");
    const content = codeRef.current;

    if (modeRef.current === "browser") {
      const all = loadBrowserFiles();
      all[name] = content;
      if (!saveBrowserFiles(all)) throw new Error("Browser storage is full. Delete some scripts and try again.");
      savedCodeRef.current = content;
      setSavedCode(content);
      setFiles((previous) => ({ ...previous, scripts: browserScriptList() }));
      return (await parseNow()) ?? parsedRef.current;
    }

    const data = await postJson<SaveResponse>("/api/save", { filename: name, code: content });
    savedCodeRef.current = content;
    setSavedCode(content);
    const result = { scenes: data.scenes, animations: data.animations };
    applyParse(result, name, content);
    void refreshFiles();
    return result;
  }, [applyParse, parseNow, refreshFiles]);

  const createFile = useCallback(
    async (name: string, content: string) => {
      if (modeRef.current === "browser") {
        const all = loadBrowserFiles();
        if (name in all) throw new Error(`${name} already exists.`);
        all[name] = content;
        if (!saveBrowserFiles(all)) throw new Error("Browser storage is full.");
      } else {
        await postJson<SaveResponse>("/api/save", { filename: name, code: content });
      }
      await refreshFiles();
      await openFile(name);
    },
    [openFile, refreshFiles],
  );

  const renameFile = useCallback(
    async (oldName: string, newName: string) => {
      if (oldName === newName) return;
      if (modeRef.current === "browser") {
        const all = loadBrowserFiles();
        if (newName in all) throw new Error(`${newName} already exists.`);
        all[newName] = all[oldName] ?? "";
        delete all[oldName];
        if (!saveBrowserFiles(all)) throw new Error("Browser storage is full.");
      } else {
        await postJson("/api/rename", { old_name: oldName, new_name: newName });
      }
      const oldKey = fileKey(modeRef.current, oldName);
      if (oldKey in draftsRef.current) {
        const draft = draftsRef.current[oldKey];
        updateDrafts((all) => ({ ...withoutKey(all, oldKey), [fileKey(modeRef.current, newName)]: draft }));
      }
      // Keep the open buffer (including unsaved edits) under its new name.
      if (activeFileRef.current === oldName) {
        activeFileRef.current = newName;
        setActiveFile(newName);
        writeStored(activeFileKey(modeRef.current), newName);
      }
      await refreshFiles();
    },
    [refreshFiles, updateDrafts],
  );

  const deleteFile = useCallback(
    async (name: string) => {
      if (modeRef.current === "browser") {
        const all = loadBrowserFiles();
        delete all[name];
        saveBrowserFiles(all);
      } else {
        await deleteRequest("/api/scripts", { filename: name });
      }
      const key = fileKey(modeRef.current, name);
      updateDrafts((all) => withoutKey(all, key));
      const next = await refreshFiles();
      if (activeFileRef.current === name) {
        // Nothing to keep from a deleted file.
        activeFileRef.current = null;
        const fallback = next?.scripts[0]?.name;
        if (fallback) await openFile(fallback).catch(() => false);
        else showBuffer(null, "");
      }
    },
    [openFile, refreshFiles, showBuffer, updateDrafts],
  );

  const uploadAsset = useCallback(
    async (file: File) => {
      const lower = file.name.toLowerCase();
      if (!ALLOWED_ASSET_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
        throw new Error(`${file.name}: unsupported type. Use ${ALLOWED_ASSET_EXTENSIONS.join(", ")}.`);
      }
      if (file.size > MAX_ASSET_SIZE_BYTES) throw new Error(`${file.name} is larger than 50 MB.`);
      const body = new FormData();
      body.append("file", file);
      await requestJson("/api/upload-asset", { method: "POST", body });
      await refreshFiles();
    },
    [refreshFiles],
  );

  const deleteAsset = useCallback(
    async (name: string) => {
      await deleteRequest("/api/assets", { filename: name });
      await refreshFiles();
    },
    [refreshFiles],
  );

  const deleteMedia = useCallback(
    async (item: MediaFile) => {
      await deleteRequest("/api/media", { path: item.path });
      await refreshFiles();
    },
    [refreshFiles],
  );

  const discardChanges = useCallback(() => setCode(savedCode), [savedCode]);

  const prefix = `${mode}:`;
  const dirtyFiles = Object.keys(drafts)
    .filter((key) => key.startsWith(prefix))
    .map((key) => key.slice(prefix.length));
  const isDirty = activeFile !== null && code !== savedCode;
  if (isDirty && activeFile) dirtyFiles.push(activeFile);

  return {
    files,
    filesStatus,
    activeFile,
    code,
    setCode,
    isDirty,
    dirtyFiles,
    hasUnsavedWork: isDirty || Object.keys(drafts).length > 0,
    discardChanges,
    scenes: parsed.scenes,
    animations: parsed.animations,
    selectedScene,
    setSelectedScene,
    refreshFiles,
    openFile,
    parseNow,
    save,
    createFile,
    renameFile,
    deleteFile,
    uploadAsset,
    deleteAsset,
    deleteMedia,
  };
}

export type Workspace = ReturnType<typeof useWorkspace>;
