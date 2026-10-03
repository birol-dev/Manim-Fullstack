import { useState } from "react";
import { Columns2, Download, FileCode2, Film, Globe, ImageIcon, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Callout, EmptyState, Section } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import { apiUrl, errorMessage } from "@/lib/api";
import { formatBytes, formatRelativeTime, toScriptName, validateScriptName } from "@/lib/format";
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

function RenameInput({
  initial,
  existing,
  onCommit,
  onCancel,
}: {
  initial: string;
  existing: string[];
  onCommit: (name: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const commit = async () => {
    if (busy) return;
    const name = toScriptName(value);
    if (name === initial || !value.trim()) return onCancel();
    const problem = validateScriptName(name, existing.filter((other) => other !== initial));
    if (problem) return setError(problem);
    setBusy(true);
    try {
      await onCommit(name);
    } catch (err) {
      setError(errorMessage(err, "Rename failed."));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-1 py-0.5">
      <input
        autoFocus
        aria-label="New file name"
        aria-invalid={error ? true : undefined}
        value={value}
        disabled={busy}
        onChange={(event) => {
          setValue(event.target.value);
          setError(null);
        }}
        onFocus={(event) => event.currentTarget.setSelectionRange(0, initial.replace(/\.py$/, "").length)}
        onKeyDown={(event) => {
          if (event.key === "Enter") void commit();
          if (event.key === "Escape") onCancel();
        }}
        onBlur={() => void commit()}
        className="h-6 w-full rounded border border-accent bg-canvas px-1.5 text-xs text-fg outline-none aria-[invalid=true]:border-danger"
      />
      {error && <p className="text-2xs text-danger">{error}</p>}
    </div>
  );
}

export function FilesPanel(props: FilesPanelProps) {
  const { files, storageMode, activeFile, dirtyFiles, previewPath } = props;
  const [renaming, setRenaming] = useState<string | null>(null);
  const scriptNames = files.scripts.map((script) => script.name);
  const videos = files.media.filter((item) => item.type === "video");

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
        {storageMode === "browser" && (
          <Callout icon={<Globe />}>Scripts are saved in this browser only. Renders still run on the server.</Callout>
        )}

        <Section title="Scripts">
          {props.filesError ? (
            <EmptyState title="Couldn't load scripts" description="The server isn't reachable. Retrying automatically." />
          ) : (
            <ul className="flex flex-col gap-px">
              {files.scripts.map((script) => {
                const active = script.name === activeFile;
                return (
                  <li
                    key={script.name}
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
                        onCancel={() => setRenaming(null)}
                        onCommit={async (name) => {
                          await props.onRename(script.name, name);
                          setRenaming(null);
                        }}
                      />
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => props.onOpen(script.name)}
                          onDoubleClick={() => setRenaming(script.name)}
                          title={`${script.name} · ${formatBytes(script.size)}`}
                          className="h-7 min-w-0 flex-1 truncate text-left text-xs"
                        >
                          {script.name}
                        </button>
                        {dirtyFiles.includes(script.name) && (
                          <span className="size-1.5 shrink-0 rounded-full bg-fg-muted group-hover:hidden" aria-label="Unsaved changes" />
                        )}
                        <RowActions>
                          <Tooltip content="Rename">
                            <Button variant="ghost" size="icon-xs" aria-label={`Rename ${script.name}`} onClick={() => setRenaming(script.name)}>
                              <Pencil />
                            </Button>
                          </Tooltip>
                          <Tooltip content="Delete">
                            <Button variant="danger-ghost" size="icon-xs" aria-label={`Delete ${script.name}`} onClick={() => props.onDelete(script.name)}>
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
            <ul className="flex flex-col gap-px">
              {files.media.map((item) => {
                const active = item.path === previewPath;
                const Icon = item.type === "image" ? ImageIcon : Film;
                const meta = [item.quality, item.script && `${item.script}.py`, formatRelativeTime(item.modified)]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <li
                    key={item.path}
                    className={cn(
                      "group relative flex items-center gap-1 rounded-md pl-2 pr-1 transition-colors",
                      active ? "bg-overlay" : "hover:bg-raised",
                    )}
                  >
                    {active && <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" />}
                    <button
                      type="button"
                      onClick={() => props.onPreviewMedia(item)}
                      title={`${item.path} · ${formatBytes(item.size)}`}
                      className="flex min-w-0 flex-1 items-center gap-2 py-1.5 text-left"
                    >
                      <Icon className={cn("size-3.5 shrink-0", active ? "text-accent" : "text-fg-subtle")} />
                      <span className="min-w-0">
                        <span className={cn("block truncate text-xs", active ? "text-fg" : "text-fg-muted")}>{item.scene}</span>
                        <span className="block truncate text-2xs text-fg-subtle">{meta}</span>
                      </span>
                    </button>
                    <RowActions>
                      <Tooltip content="Download">
                        <Button asChild variant="ghost" size="icon-xs">
                          <a href={apiUrl(item.url)} download={item.name} aria-label={`Download ${item.name}`}>
                            <Download />
                          </a>
                        </Button>
                      </Tooltip>
                      <Tooltip content="Delete">
                        <Button variant="danger-ghost" size="icon-xs" aria-label={`Delete render ${item.name}`} onClick={() => props.onDeleteMedia(item)}>
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
