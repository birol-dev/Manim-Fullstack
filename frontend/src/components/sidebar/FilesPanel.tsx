import { useEffect, useRef, useState } from "react";
import { Columns2, Download, FileCode2, Film, Globe, ImageIcon, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { FileNameText } from "@/components/ui/code-text";
import { Callout, EmptyState, Section } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import { apiUrl, errorMessage } from "@/lib/api";
import { dedupeExtension, formatBytes, formatRelativeTime, toScriptName, validateScriptName } from "@/lib/format";
import type { MediaFile, StorageMode, WorkspaceFiles } from "@/lib/types";
import { cn } from "@/lib/utils";
import { RowActions, SidebarPanel } from "./SidebarPanel";

interface FilesPanelProps {
  files: WorkspaceFiles;
  filesError: boolean;
  storageMode: StorageMode;
  activeFile: string | null;
  dirtyFiles: string[];
  previewPath: string | null;
  onOpen: (name: string) => void;
  onNew: () => void;
  onRename: (oldName: string, newName: string) => Promise<void>;
  onDelete: (name: string) => void;
  onRefresh: () => void;
  onPreviewMedia: (item: MediaFile) => void;
  onDeleteMedia: (item: MediaFile) => void;
  onCompare: () => void;
}

/**
 * Inline rename. The name is checked while typing (same rule and wording as the
 * New script dialog); Enter/Escape hand focus back to the row (*keyboard*), a
 * click elsewhere commits without taking focus back.
 */
function RenameInput({
  initial,
  existing,
  onCommit,
  onCancel,
}: {
  initial: string;
  existing: string[];
  onCommit: (name: string, keyboard: boolean) => Promise<void>;
  onCancel: (keyboard: boolean) => void;
}) {
  const [value, setValue] = useState(initial);
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const name = toScriptName(value);
  const unchanged = name === initial || !value.trim();
  const problem = unchanged ? null : validateScriptName(name, existing.filter((other) => other !== initial));
  const error = serverError ?? problem;

  const commit = async (keyboard: boolean) => {
    if (busy) return;
    if (unchanged) return onCancel(keyboard);
    if (problem) return;
    setBusy(true);
    try {
      await onCommit(name, keyboard);
    } catch (err) {
      setServerError(errorMessage(err, "Couldn't rename the file."));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-1 py-0.5">
      <input
        autoFocus
        aria-label="New file name"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "rename-error" : undefined}
        value={value}
        disabled={busy}
        onChange={(event) => {
          setValue(dedupeExtension(event.target.value));
          setServerError(null);
        }}
        onFocus={(event) => event.currentTarget.setSelectionRange(0, initial.replace(/\.py$/i, "").length)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void commit(true);
          } else if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            onCancel(true);
          }
        }}
        onBlur={() => void commit(false)}
        className="h-6 w-full rounded border border-accent bg-canvas px-1.5 text-xs text-fg outline-none aria-[invalid=true]:border-danger"
      />
      {error ? (
        <p id="rename-error" role="alert" className="text-2xs text-danger">
          {error}
        </p>
      ) : (
        !unchanged && name !== value.trim() && <p className="text-2xs text-fg-subtle">Will be saved as {name}</p>
      )}
    </div>
  );
}

/**
 * One Tab stop per list (roving tabindex): Tab reaches the current row and the
 * next Tab leaves the list. Up/Down, Home, and End move between rows;
 * Right/Left move between a row and its actions, which are never Tab stops.
 */
function useRovingList(keys: string[], preferred: string | null) {
  const [current, setCurrent] = useState<string | null>(null);
  const focusKey = [current, preferred, keys[0]].find((key) => key != null && keys.includes(key)) ?? null;

  const onKeyDown = (event: React.KeyboardEvent<HTMLUListElement>) => {
    const target = event.target as HTMLElement;
    if (target.tagName === "INPUT") return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      const controls = Array.from(
        target.closest("li")?.querySelectorAll<HTMLElement>("[data-roving-item], [data-row-action]") ?? [],
      );
      const index = controls.indexOf(target);
      if (index < 0) return;
      event.preventDefault();
      const step = event.key === "ArrowRight" ? 1 : -1;
      controls[Math.max(0, Math.min(controls.length - 1, index + step))].focus();
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("[data-roving-item]"));
    if (items.length === 0) return;
    const row = target.closest("li")?.querySelector<HTMLElement>("[data-roving-item]");
    const index = row ? items.indexOf(row) : -1;
    const next =
      event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : event.key === "ArrowDown" ? index + 1 : index - 1;
    event.preventDefault();
    items[Math.max(0, Math.min(items.length - 1, next))].focus();
  };

  return { focusKey, setCurrent, onKeyDown };
}

export function FilesPanel(props: FilesPanelProps) {
  const { files, storageMode, activeFile, dirtyFiles, previewPath } = props;
  const [renaming, setRenaming] = useState<string | null>(null);
  // After a keyboard rename (Enter/Escape), focus goes back to that row, under its new name.
  const refocusRow = useRef<string | null>(null);
  const scriptListRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    const name = refocusRow.current;
    if (!name || renaming) return;
    const row = Array.from(scriptListRef.current?.querySelectorAll<HTMLElement>("[data-roving-item]") ?? []).find(
      (element) => element.dataset.name === name,
    );
    if (!row) return; // the list hasn't caught up with a rename yet
    refocusRow.current = null;
    row.focus();
  });
  const startRename = (name: string) => {
    refocusRow.current = null;
    setRenaming(name);
  };
  const scriptNames = files.scripts.map((script) => script.name);
  const videos = files.media.filter((item) => item.type === "video");
  const scriptRoving = useRovingList(scriptNames, activeFile);
  const mediaRoving = useRovingList(
    files.media.map((item) => item.path),
    previewPath,
  );

  return (
    <SidebarPanel
      title="Files"
      actions={
        <>
          <Tooltip content="Refresh">
            <Button variant="ghost" size="icon-xs" aria-label="Refresh files" onClick={props.onRefresh}>
              <RefreshCw />
            </Button>
          </Tooltip>
          <Tooltip content="New script">
            <Button variant="ghost" size="icon-xs" aria-label="New script" onClick={props.onNew}>
              <Plus />
            </Button>
          </Tooltip>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <p id="script-row-keys" hidden>
          Right arrow reaches Rename and Delete. F2 renames, Delete deletes.
        </p>
        <p id="render-row-keys" hidden>
          Right arrow reaches Download and Delete. Delete removes the render.
        </p>
        {storageMode === "browser" && (
          <Callout icon={<Globe />}>Scripts are saved in this browser only. Renders still run on the server.</Callout>
        )}

        <Section title="Scripts">
          {props.filesError ? (
            <EmptyState title="Couldn't load scripts" description="The server isn't reachable. Retrying automatically." />
          ) : (
            <ul ref={scriptListRef} aria-label="Scripts" className="flex flex-col gap-px" onKeyDown={scriptRoving.onKeyDown}>
              {files.scripts.map((script) => {
                const active = script.name === activeFile;
                const tabIndex = script.name === scriptRoving.focusKey ? 0 : -1;
                // Links out of the workspace (or to nothing) can't be opened; offer Delete only.
                const linkNote = script.outside
                  ? "link to a file outside the workspace"
                  : script.broken
                    ? "broken link"
                    : null;
                return (
                  <li
                    key={script.name}
                    onFocus={() => scriptRoving.setCurrent(script.name)}
                    className={cn(
                      "group relative flex min-h-7 items-center gap-1 rounded-md pl-2 pr-1 transition-colors",
                      active ? "bg-overlay text-fg" : "text-fg-muted hover:bg-raised hover:text-fg",
                    )}
                  >
                    {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-accent" />}
                    <FileCode2 className={cn("size-3.5 shrink-0", active ? "text-accent" : "text-fg-subtle")} />
                    {renaming === script.name ? (
                      <RenameInput
                        initial={script.name}
                        existing={scriptNames}
                        onCancel={(keyboard) => {
                          if (keyboard) refocusRow.current = script.name;
                          setRenaming(null);
                        }}
                        onCommit={async (name, keyboard) => {
                          await props.onRename(script.name, name);
                          if (keyboard) refocusRow.current = name;
                          setRenaming(null);
                        }}
                      />
                    ) : (
                      <>
                        <button
                          type="button"
                          data-roving-item
                          data-name={script.name}
                          tabIndex={tabIndex}
                          aria-current={active ? "true" : undefined}
                          onClick={() => {
                            if (!linkNote) props.onOpen(script.name);
                          }}
                          onDoubleClick={() => {
                            if (!linkNote) startRename(script.name);
                          }}
                          aria-disabled={linkNote ? "true" : undefined}
                          onKeyDown={(event) => {
                            if (event.key === "F2" && !linkNote) startRename(script.name);
                            else if (event.key === "Delete") props.onDelete(script.name);
                            else return;
                            event.preventDefault();
                          }}
                          aria-keyshortcuts="F2 Delete ArrowRight"
                          aria-describedby="script-row-keys"
                          title={linkNote ? `${script.name} · ${linkNote} (can only be deleted)` : `${script.name} · ${formatBytes(script.size)}`}
                          className={cn("h-7 min-w-0 flex-1 truncate text-left text-xs", linkNote && "italic text-fg-subtle")}
                        >
                          {script.name}
                          {linkNote && <span className="sr-only"> ({linkNote}, can only be deleted)</span>}
                        </button>
                        {dirtyFiles.includes(script.name) && (
                          <span className="size-1.5 shrink-0 rounded-full bg-fg-muted group-hover:hidden" aria-label="Unsaved changes" />
                        )}
                        <RowActions>
                          {!linkNote && (
                            <Tooltip content="Rename">
                              <Button
                                variant="ghost"
                                size="icon-xs"
                                tabIndex={-1}
                                data-row-action
                                aria-label={`Rename ${script.name}`}
                                onClick={() => startRename(script.name)}
                              >
                                <Pencil />
                              </Button>
                            </Tooltip>
                          )}
                          <Tooltip content="Delete">
                            <Button
                              variant="danger-ghost"
                              size="icon-xs"
                              tabIndex={-1}
                              data-row-action
                              aria-label={`Delete ${script.name}`}
                              onClick={() => props.onDelete(script.name)}
                            >
                              <Trash2 />
                            </Button>
                          </Tooltip>
                        </RowActions>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Section>

        <Section
          title={`Renders${files.media.length ? ` · ${files.media.length}` : ""}`}
          actions={
            videos.length > 1 && (
              <Tooltip content="Compare two renders">
                <Button variant="ghost" size="icon-xs" aria-label="Compare renders" onClick={props.onCompare}>
                  <Columns2 />
                </Button>
              </Tooltip>
            )
          }
        >
          {files.media.length === 0 ? (
            <p className="px-1 text-xs text-fg-subtle">Rendered videos and images show up here.</p>
          ) : (
            <ul aria-label="Renders" className="flex flex-col gap-px" onKeyDown={mediaRoving.onKeyDown}>
              {files.media.map((item) => {
                const active = item.path === previewPath;
                const tabIndex = item.path === mediaRoving.focusKey ? 0 : -1;
                const Icon = item.type === "image" ? ImageIcon : Film;
                // "720p30 · just now" stays together; the script name follows, or wraps to its own line.
                const when = [item.quality, formatRelativeTime(item.modified)].filter(Boolean).join(" · ");
                const script = item.script ? `${item.script}.py` : null;
                return (
                  <li
                    key={item.path}
                    onFocus={() => mediaRoving.setCurrent(item.path)}
                    className={cn(
                      "group relative flex items-center gap-1 rounded-md pl-2 pr-1 transition-colors",
                      active ? "bg-overlay" : "hover:bg-raised",
                    )}
                  >
                    {active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" />}
                    <button
                      type="button"
                      data-roving-item
                      tabIndex={tabIndex}
                      aria-current={active ? "true" : undefined}
                      onClick={() => props.onPreviewMedia(item)}
                      onKeyDown={(event) => {
                        if (event.key !== "Delete") return;
                        event.preventDefault();
                        props.onDeleteMedia(item);
                      }}
                      aria-keyshortcuts="Delete ArrowRight"
                      aria-describedby="render-row-keys"
                      title={`${item.path} · ${formatBytes(item.size)}`}
                      className="flex min-w-0 flex-1 items-center gap-2 py-1.5 text-left"
                    >
                      <Icon className={cn("size-3.5 shrink-0", active ? "text-accent" : "text-fg-subtle")} />
                      <span className="min-w-0">
                        {/* Wraps at camelCase / "_" steps instead of "CircleToSqu…" in a narrow sidebar. */}
                        <span className={cn("code-wrap block text-xs text-fg", active && "font-medium")}>
                          <FileNameText name={item.scene} />
                        </span>
                        {/* 12px fg-muted: >= 6.5:1 on every row background (fg-subtle 11px was 4.1:1 on the selected row).
                            The script name wraps under the quality instead of being cut ("720p30 · qa_…"). */}
                        <span className="flex flex-wrap gap-x-2 text-xs text-fg-muted">
                          <span className="whitespace-nowrap">{when}</span>
                          {script && (
                            <span className="code-wrap min-w-0">
                              <FileNameText name={script} />
                            </span>
                          )}
                        </span>
                      </span>
                    </button>
                    <RowActions>
                      <Tooltip content="Download">
                        <Button asChild variant="ghost" size="icon-xs">
                          <a
                            href={apiUrl(item.url)}
                            download={item.name}
                            tabIndex={-1}
                            data-row-action
                            aria-label={`Download ${item.name}`}
                          >
                            <Download />
                          </a>
                        </Button>
                      </Tooltip>
                      <Tooltip content="Delete">
                        <Button
                          variant="danger-ghost"
                          size="icon-xs"
                          tabIndex={-1}
                          data-row-action
                          aria-label={`Delete render ${item.name}`}
                          onClick={() => props.onDeleteMedia(item)}
                        >
                          <Trash2 />
                        </Button>
                      </Tooltip>
                    </RowActions>
                  </li>
                );
              })}
            </ul>
          )}
        </Section>
      </div>
    </SidebarPanel>
  );
}
