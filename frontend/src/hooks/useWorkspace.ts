import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ApiError, deleteRequest, errorMessage, postJson, requestJson } from "@/lib/api";
import { ALLOWED_ASSET_EXTENSIONS, MAX_ASSET_SIZE_BYTES, formatByteLimit, getMaxCodeBytes } from "@/lib/constants";
import { loadBrowserFiles, readStored, saveBrowserFiles, STORAGE_KEYS, writeStored } from "@/lib/storage";
import type { MediaFile, ParseResult, ScriptFile, StorageMode, WorkspaceFiles } from "@/lib/types";

/**
 * The file changed on disk since this tab loaded it ("changed"), or it was
 * renamed or deleted elsewhere ("missing"). Nothing was written.
 */
/** current_version from a 412 body, else its ETag (quotes and a weak W/ prefix removed). */
export function conflictVersion(err: ApiError): string | null {
  const fromBody = (err.body as { current_version?: unknown } | null)?.current_version;
  if (typeof fromBody === "string" && fromBody) return fromBody;
  const tag = err.etag?.replace(/^W\//, "").replace(/^"|"$/g, "");
  return tag || null;
}

export class SaveConflictError extends ApiError {
  readonly reason: "changed" | "missing";
  readonly filename: string;

  /** The version on disk now (a 412's current_version / ETag), so Overwrite needs no extra fetch. */
  readonly currentVersion: string | null;

  constructor(message: string, status: number, filename: string, currentVersion: string | null = null) {
    super(message, status);
    this.name = "SaveConflictError";
    this.reason = status === 404 ? "missing" : "changed";
    this.filename = filename;
    this.currentVersion = currentVersion;
  }
}

export interface SaveOptions {
  /** Write without any version check (Recreate a deleted file). */
  force?: boolean;
  /**
   * Overwrite exactly this version (the one a conflict reported): the save still
   * conflicts if the file changed yet again in the meantime.
   */
  overwriteVersion?: string;
}

const EMPTY_FILES: WorkspaceFiles = { scripts: [], assets: [], media: [] };
const EMPTY_PARSE: ParseResult = { scenes: [], animations: {}, syntaxError: null };

interface ServerParse {
  scenes?: string[];
  animations?: ParseResult["animations"];
  syntax_error?: ParseResult["syntaxError"];
}

function asParseResult(data: ServerParse | null | undefined): ParseResult {
  return {
    scenes: data?.scenes ?? [],
    animations: data?.animations ?? {},
    syntaxError: data?.syntax_error ?? null,
  };
}

function assertCodeSize(code: string) {
  const limit = getMaxCodeBytes();
  if (new TextEncoder().encode(code).length > limit) {
    throw new ApiError(`This script is larger than ${formatByteLimit(limit)}, so it can't be saved or rendered.`, 413);
  }
}
const PARSE_DEBOUNCE_MS = 400;

export type FilesStatus = "loading" | "ready" | "error";

interface FileContentResponse extends ServerParse {
  filename: string;
  code: string;
  /** Opaque version of the file on disk, sent back on save to detect conflicts. */
  version?: string;
}

interface SaveResponse extends ServerParse {
  filename: string;
  version?: string;
}

function browserScriptList(): ScriptFile[] {
  const encoder = new TextEncoder();
  return Object.entries(loadBrowserFiles())
    .map(([name, content]) => ({ name, size: encoder.encode(content).length, type: "script" as const }))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}

function parseCode(code: string): Promise<ParseResult> {
  assertCodeSize(code);
  return postJson<ServerParse>("/api/parse-code", { code }).then(asParseResult);
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
  // "mode:file" -> version of the file on disk that the buffer (or draft) is based on.
  const versionsRef = useRef<Record<string, string>>({});
  const savesInFlight = useRef(0);
  // "mode:file" -> a scene name typed with "Other scene…" that the parser can't see (kept across reloads).
  const typedScenesRef = useRef<Record<string, string>>(readStored<Record<string, string>>(STORAGE_KEYS.typedSceneByFile, {}));
  // Browser storage: file -> the content this tab's buffer is based on (what it loaded or
  // last saved). Another tab writing something else in between is a conflict.
  const browserBaseRef = useRef<Record<string, string>>({});
  // While a save-conflict dialog is open, notices about outside changes wait.
  const noticesHeldRef = useRef(false);

  useEffect(() => {
    codeRef.current = code;
  }, [code]);
  // Typing updates the ref at once: Ctrl+S (or another tab's storage event) right after
  // a keystroke must see that keystroke, not the last committed render.
  const editCode = useCallback((next: string) => {
    codeRef.current = next;
    setCode(next);
  }, []);

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
    const typed = file ? typedScenesRef.current[fileKey(modeRef.current, file)] : undefined;
    setSelectedSceneState((previous) => {
      if (previous && (result.scenes.includes(previous) || previous === typed)) return previous;
      if (remembered && (result.scenes.includes(remembered) || remembered === typed)) return remembered;
      return result.scenes[0] ?? "";
    });
  }, []);

  const setSelectedScene = useCallback((scene: string) => {
    setSelectedSceneState(scene);
    const file = activeFileRef.current;
    if (!file) return;
    // A name the parser didn't find was typed in: keep it selected while the code changes, and after a reload.
    if (scene && !parsedRef.current.scenes.includes(scene)) {
      typedScenesRef.current = { ...typedScenesRef.current, [fileKey(modeRef.current, file)]: scene };
      writeStored(STORAGE_KEYS.typedSceneByFile, typedScenesRef.current);
    }
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
        const stored = loadBrowserFiles()[name] ?? "";
        // A restored draft stays based on what it was edited from.
        if (!(fileKey("browser", name) in draftsRef.current && name in browserBaseRef.current)) browserBaseRef.current[name] = stored;
        showBuffer(name, stored);
        parsedCodeRef.current = null; // parsed by the debounced effect
        return true;
      }
      const data = await requestJson<FileContentResponse>(`/api/file-content?filename=${encodeURIComponent(name)}`);
      if (seq !== loadSeq.current) return false;
      const key = fileKey(modeRef.current, data.filename);
      // An unsaved draft stays based on the version it was edited from, so saving it
      // still notices changes made elsewhere in the meantime.
      const keepVersion = key in draftsRef.current && key in versionsRef.current;
      if (!keepVersion && data.version) versionsRef.current[key] = data.version;
      showBuffer(data.filename, data.code);
      applyParse(asParseResult(data), data.filename, data.code);
      return true;
    },
    [applyParse, showBuffer],
  );

  const initialize = useCallback(async () => {
    const next = await refreshFiles();
    if (!next) return;
    // Links out of the workspace are listed (so they can be deleted) but can't be opened.
    const names = next.scripts.filter((script) => !script.outside && !script.broken).map((script) => script.name);
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
      const result = await parseCode(source).catch((err: unknown) => {
        if (codeRef.current === source && err instanceof ApiError && err.status === 413) {
          toast.error(err.message, { id: "code-size" });
        }
        return null;
      });
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

  /**
   * Save the buffer. Resolves with the scenes it contains; throws on failure, with
   * a SaveConflictError when the file changed or disappeared on disk. *force*
   * writes anyway (the user chose "Overwrite" or "Recreate").
   */
  const save = useCallback(async (options?: SaveOptions): Promise<ParseResult> => {
    const name = activeFileRef.current;
    if (!name) throw new Error("No file is open.");
    const mode = modeRef.current;
    const content = codeRef.current;
    assertCodeSize(content);
    // The user may open another file while the request is in flight.
    const stillOpen = () => modeRef.current === mode && activeFileRef.current === name;

    const markSaved = () => {
      if (stillOpen()) {
        savedCodeRef.current = content;
        setSavedCode(content);
        return;
      }
      // Switching away stashed the buffer as a draft; drop it if that's exactly what was saved.
      const key = fileKey(mode, name);
      if (draftsRef.current[key] === content) updateDrafts((all) => withoutKey(all, key));
    };

    if (mode === "browser") {
      const all = loadBrowserFiles();
      // Same rules as the server's base_version check: another tab saved or removed the file.
      const base = browserBaseRef.current[name];
      if (!options?.force && !options?.overwriteVersion && base !== undefined) {
        if (!(name in all)) throw new SaveConflictError("This file was renamed or deleted in another tab.", 404, name);
        if (all[name] !== base && all[name] !== content) {
          throw new SaveConflictError("This file was changed in another tab since you opened it.", 412, name);
        }
      }
      all[name] = content;
      if (!saveBrowserFiles(all)) throw new Error("Browser storage is full. Delete some scripts and try again.");
      browserBaseRef.current[name] = content;
      markSaved();
      setFiles((previous) => ({ ...previous, scripts: browserScriptList() }));
      try {
        return (await parseNow()) ?? parsedRef.current;
      } catch (err) {
        if (err instanceof ApiError && err.status === 413) throw err;
        return parsedRef.current;
      }
    }

    const key = fileKey(mode, name);
    const baseVersion = options?.overwriteVersion ?? (options?.force ? undefined : versionsRef.current[key]);
    let data: SaveResponse;
    savesInFlight.current += 1;
    try {
      data = await postJson<SaveResponse>("/api/save", { filename: name, code: content, base_version: baseVersion });
    } catch (err) {
      if (err instanceof ApiError && (err.status === 412 || (err.status === 404 && baseVersion !== undefined))) {
        throw new SaveConflictError(err.message, err.status, name, err.status === 412 ? conflictVersion(err) : null);
      }
      throw err;
    } finally {
      savesInFlight.current -= 1;
    }
    if (data.version) versionsRef.current[key] = data.version;
    markSaved();
    const result = asParseResult(data);
    if (stillOpen()) applyParse(result, name, content);
    void refreshFiles();
    return result;
  }, [applyParse, parseNow, refreshFiles, updateDrafts]);

  const createFile = useCallback(
    async (name: string, content: string) => {
      let created = name;
      if (modeRef.current === "browser") {
        const all = loadBrowserFiles();
        if (name in all) throw new Error(`${name} already exists.`);
        all[name] = content;
        if (!saveBrowserFiles(all)) throw new Error("Browser storage is full.");
        browserBaseRef.current[name] = content;
      } else {
        const data = await postJson<SaveResponse>("/api/save", { filename: name, code: content, create_only: true });
        if (data.version) versionsRef.current[fileKey("disk", data.filename)] = data.version;
        // The server stores the normalized name (NFC, lowercase .py); open that one.
        if (data.filename) created = data.filename;
      }
      await refreshFiles();
      await openFile(created);
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
        if (oldName in browserBaseRef.current) {
          browserBaseRef.current[newName] = browserBaseRef.current[oldName];
          delete browserBaseRef.current[oldName];
        }
      } else {
        await postJson("/api/rename", { old_name: oldName, new_name: newName });
      }
      const oldKey = fileKey(modeRef.current, oldName);
      if (oldKey in versionsRef.current) {
        versionsRef.current[fileKey(modeRef.current, newName)] = versionsRef.current[oldKey];
        delete versionsRef.current[oldKey];
      }
      // The scene picked or typed for the file follows it.
      const newKey = fileKey(modeRef.current, newName);
      if (oldKey in typedScenesRef.current) {
        const { [oldKey]: typed, ...rest } = typedScenesRef.current;
        typedScenesRef.current = { ...rest, [newKey]: typed };
        writeStored(STORAGE_KEYS.typedSceneByFile, typedScenesRef.current);
      }
      const sceneMemory = readStored<Record<string, string>>(STORAGE_KEYS.sceneByFile, {});
      if (oldKey in sceneMemory) {
        const { [oldKey]: scene, ...rest } = sceneMemory;
        writeStored(STORAGE_KEYS.sceneByFile, { ...rest, [newKey]: scene });
      }
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
        delete browserBaseRef.current[name];
      } else {
        await deleteRequest("/api/scripts", { filename: name });
      }
      const key = fileKey(modeRef.current, name);
      delete versionsRef.current[key];
      updateDrafts((all) => withoutKey(all, key));
      const next = await refreshFiles();
      if (activeFileRef.current === name) {
        // Nothing to keep from a deleted file.
        activeFileRef.current = null;
        const fallback = next?.scripts.find((script) => !script.outside && !script.broken)?.name;
        if (fallback) await openFile(fallback).catch(() => false);
        else showBuffer(null, "");
      }
    },
    [openFile, refreshFiles, showBuffer, updateDrafts],
  );

  /** Replace the open buffer with the file on disk ("Reload theirs"); unsaved edits are dropped. */
  const reloadFromDisk = useCallback(async () => {
    const name = activeFileRef.current;
    if (!name) return;
    if (modeRef.current === "browser") {
      const stored = loadBrowserFiles()[name];
      if (stored === undefined) return;
      browserBaseRef.current[name] = stored;
      codeRef.current = stored;
      savedCodeRef.current = stored;
      setCode(stored);
      setSavedCode(stored);
      parsedCodeRef.current = null; // parsed by the debounced effect
      return;
    }
    const seq = ++loadSeq.current;
    const data = await requestJson<FileContentResponse>(`/api/file-content?filename=${encodeURIComponent(name)}`);
    if (seq !== loadSeq.current || activeFileRef.current !== name) return;
    const key = fileKey(modeRef.current, name);
    if (data.version) versionsRef.current[key] = data.version;
    codeRef.current = data.code;
    savedCodeRef.current = data.code;
    setCode(data.code);
    setSavedCode(data.code);
    applyParse(asParseResult(data), name, data.code);
  }, [applyParse]);

  /**
   * When the tab regains focus, look for changes made to the open file elsewhere.
   * A clean buffer reloads quietly; edits are kept and the user is told.
   */
  const checkOpenFile = useCallback(async () => {
    const name = activeFileRef.current;
    if (!name || modeRef.current !== "disk" || savesInFlight.current > 0 || noticesHeldRef.current) return;
    const key = fileKey("disk", name);
    const known = versionsRef.current[key];
    const seq = loadSeq.current;
    let data: FileContentResponse;
    try {
      data = await requestJson<FileContentResponse>(`/api/file-content?filename=${encodeURIComponent(name)}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404 && activeFileRef.current === name && !noticesHeldRef.current) {
        toast.warning(`${name} was renamed or deleted elsewhere`, {
          id: "external-change",
          description: "Your text is still here. Saving asks before recreating the file.",
          action: {
            label: "Recreate file",
            onClick: () =>
              void save({ force: true }).then(
                () => refreshFiles(),
                (error) => toast.error(errorMessage(error, "Couldn't recreate the file.")),
              ),
          },
        });
        void refreshFiles();
      }
      return;
    }
    const unchanged = !data.version || data.version === known;
    if (unchanged || seq !== loadSeq.current || activeFileRef.current !== name || savesInFlight.current > 0 || noticesHeldRef.current) return;
    if (data.code === codeRef.current || codeRef.current === savedCodeRef.current) {
      // Same text, or nothing unsaved here: take the file as it is on disk now.
      const reloaded = data.code !== codeRef.current;
      versionsRef.current[key] = data.version!;
      codeRef.current = data.code;
      savedCodeRef.current = data.code;
      setCode(data.code);
      setSavedCode(data.code);
      applyParse(asParseResult(data), name, data.code);
      if (reloaded) toast.info(`Reloaded ${name}`, { id: "external-change", description: "It was changed in another tab or program." });
      return;
    }
    toast.warning(`${name} changed in another tab`, {
      id: "external-change",
      description: "You have unsaved edits here. Saving will ask which version to keep.",
      action: { label: "Reload theirs", onClick: () => void reloadFromDisk() },
    });
  }, [applyParse, refreshFiles, reloadFromDisk, save]);

  /** The Refresh button: reload the lists and notice if the open file changed or vanished on disk. */
  const refresh = useCallback(async () => {
    await refreshFiles();
    if (modeRef.current === "disk") await checkOpenFile();
  }, [refreshFiles, checkOpenFile]);

  useEffect(() => {
    if (mode !== "disk") return;
    const onFocus = () => {
      if (document.visibilityState !== "hidden") void checkOpenFile();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [mode, checkOpenFile]);

  // Browser storage: another tab saved, renamed, or deleted scripts (the "storage" event
  // only fires in the other tabs). Same handling as a file changed on disk.
  useEffect(() => {
    if (mode !== "browser") return;
    const onStorage = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEYS.browserFiles && event.key !== null) return;
      setFiles((previous) => ({ ...previous, scripts: browserScriptList() }));
      const name = activeFileRef.current;
      if (!name || noticesHeldRef.current || modeRef.current !== "browser") return;
      const stored = loadBrowserFiles()[name];
      const base = browserBaseRef.current[name];
      if (stored === base) return;
      if (stored === undefined) {
        toast.warning(`${name} was renamed or deleted in another tab`, {
          id: "external-change",
          description: "Your text is still here. Saving asks before recreating the file.",
        });
        return;
      }
      if (stored === codeRef.current || codeRef.current === savedCodeRef.current) {
        const reloaded = stored !== codeRef.current;
        browserBaseRef.current[name] = stored;
        codeRef.current = stored;
        savedCodeRef.current = stored;
        setCode(stored);
        setSavedCode(stored);
        parsedCodeRef.current = null;
        if (reloaded) toast.info(`Reloaded ${name}`, { id: "external-change", description: "It was changed in another tab." });
        return;
      }
      toast.warning(`${name} changed in another tab`, {
        id: "external-change",
        description: "You have unsaved edits here. Saving will ask which version to keep.",
        action: { label: "Reload theirs", onClick: () => void reloadFromDisk() },
      });
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [mode, reloadFromDisk]);

  /** Hold (true) or release notices about outside changes, e.g. while a save-conflict dialog is open. */
  const holdExternalNotices = useCallback((hold: boolean) => {
    noticesHeldRef.current = hold;
  }, []);

  const uploadAsset = useCallback(
    async (file: File, options?: { overwrite?: boolean }) => {
      const lower = file.name.toLowerCase();
      if (!ALLOWED_ASSET_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
        throw new Error(`${file.name}: unsupported type. Use ${ALLOWED_ASSET_EXTENSIONS.join(", ")}.`);
      }
      if (file.size > MAX_ASSET_SIZE_BYTES) throw new Error(`${file.name} is larger than 50 MB.`);
      const body = new FormData();
      body.append("file", file);
      const path = options?.overwrite ? "/api/upload-asset?overwrite=true" : "/api/upload-asset";
      await requestJson(path, { method: "POST", body });
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
    setCode: editCode,
    isDirty,
    dirtyFiles,
    hasUnsavedWork: isDirty || Object.keys(drafts).length > 0,
    discardChanges,
    scenes: parsed.scenes,
    syntaxError: parsed.syntaxError ?? null,
    animations: parsed.animations,
    selectedScene,
    /** The selected scene was typed in ("Other scene…"), not found by the parser. */
    selectedSceneTyped: selectedScene !== "" && !parsed.scenes.includes(selectedScene),
    setSelectedScene,
    refreshFiles,
    refresh,
    openFile,
    parseNow,
    save,
    reloadFromDisk,
    holdExternalNotices,
    createFile,
    renameFile,
    deleteFile,
    uploadAsset,
    deleteAsset,
    deleteMedia,
  };
}

export type Workspace = ReturnType<typeof useWorkspace>;
