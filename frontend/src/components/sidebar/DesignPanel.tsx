import { useMemo, useState } from "react";
import { ArrowUpRight, Copy, FileCode2, Film, Play, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AuthorActivity, AuthorActivityItem } from "@/hooks/useAuthorActivity";
import { designFields, replaceDesignField } from "@/lib/designFields";

interface DesignPanelProps {
  activity: AuthorActivity | null;
  unreachable: boolean;
  workspaceStorage: boolean;
  activeFile: string | null;
  code: string;
  onCodeChange: (code: string) => void;
  canRender: boolean;
  dirty: boolean;
  onSave: () => void;
  onRender: () => void;
  onWorkspaceStorage: () => void;
  onOpen: (item: AuthorActivityItem) => void;
  onUseStarter: () => void;
}

function describe(item: AuthorActivityItem) {
  if (item.kind === "script") return "Saved Python";
  if (item.status === "queued") return "Queued";
  if (item.status === "rendering") return `Rendering · ${Math.round(item.progress)}%`;
  if (item.status === "cancelled") return "Stopped";
  return item.status === "done" ? "Rendered" : "Render failed";
}

export function DesignPanel({ activity, unreachable, workspaceStorage, activeFile, code, onCodeChange, canRender, dirty, onSave, onRender, onWorkspaceStorage, onOpen, onUseStarter }: DesignPanelProps) {
  const [direction, setDirection] = useState("");
  const [editOpenFile, setEditOpenFile] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "fallback">("idle");
  const fields = useMemo(() => activeFile ? designFields(code) : [], [activeFile, code]);
  const prompt = [
    "Work with me in Manim Studio's Design Studio. Use the connected Manim Studio MCP and read guide(\"broll\").",
    activeFile && editOpenFile ? `Work on ${activeFile}. Read it first and use its current version when saving.` : "Create a new, clearly named Python script for this shot.",
    "Expose useful text and colors as top-level string constants with a # studio: Label comment so I can adjust them from the design panel.",
    "Write an original Manim scene, render a low-quality draft, and inspect its contact sheet. Keep the script editable and give me the Design Studio link so I can review the motion.",
    direction.trim() && `Design direction\n${direction.trim()}`,
  ].filter(Boolean).join("\n\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopyState("copied");
    } catch {
      setCopyState("fallback");
    }
  };

  return <section className="author-design" aria-label="Design Studio">
    <div className="author-design-heading">
      <span className="author-kicker"><Sparkles aria-hidden /> Original motion</span>
      <h2>Design Studio</h2>
      <p>Watch your agent build a shot. Open its script to edit and render the same scene.</p>
    </div>
    <Button variant="secondary" size="sm" onClick={onUseStarter}><Film /> Try Index lookup</Button>
    {fields.length > 0 && <div className="author-design-brief">
      <h3 className="author-kicker">Scene controls</h3>
      {fields.map((field, index) => <label className="author-design-field" key={index}>
        <span>{field.label}</span>
        <input type={field.type} value={field.value} maxLength={120}
          onChange={(event) => onCodeChange(replaceDesignField(code, field, event.target.value))} />
      </label>)}
      <Button variant="primary" size="sm" onClick={onRender} disabled={!canRender}><Play /> Render scene</Button>
      {dirty && <Button variant="secondary" size="sm" onClick={onSave}>Save script</Button>}
    </div>}
    {!workspaceStorage ? <div className="author-design-note">
      <p>Use workspace files to share scripts with an agent.</p>
      <Button variant="secondary" size="sm" onClick={onWorkspaceStorage}>Use workspace files</Button>
    </div> : unreachable ? <p className="author-design-note">Waiting for the Studio server to reconnect.</p>
      : activity?.enabled === false ? <div className="author-design-note">
        <p>Connect an AI app and turn on Python authoring to see its work here.</p>
        {/* A full navigation lets the editor's unsaved-work guard run. */}
        <Button asChild variant="secondary" size="sm"><a href={`${import.meta.env.BASE_URL}?from=author#/settings/ai`}>Open AI settings <ArrowUpRight /></a></Button>
      </div> : activity?.enabled ? <div className="author-design-brief">
        <label htmlFor="author-design-direction">Give the shot a direction</label>
        <textarea id="author-design-direction" maxLength={1200} rows={3} value={direction}
          placeholder="Trace one lookup and hold on the match."
          onChange={(event) => { setDirection(event.target.value); setCopyState("idle"); }} />
        {activeFile && <label className="author-design-target">
          <input type="checkbox" checked={editOpenFile} onChange={(event) => { setEditOpenFile(event.target.checked); setCopyState("idle"); }} />
          Edit open script
        </label>}
        <Button variant="secondary" size="sm" onClick={() => void copy()}><Copy />{copyState === "copied" ? "Brief copied" : "Copy scene brief"}</Button>
        {copyState === "fallback" && <textarea aria-label="Scene brief" readOnly value={prompt} onFocus={(event) => event.currentTarget.select()} />}
      </div> : <p className="author-design-note">Connecting to the workspace…</p>}
    <div className="author-design-activity">
      <h3 className="author-kicker">Agent activity</h3>
      {activity?.items.length ? <ol>{activity.items.map((item) => <li key={item.id}>
        <button type="button" onClick={() => onOpen(item)} title={`Open ${item.filename}`}>
          {item.kind === "script" ? <FileCode2 aria-hidden /> : <Film aria-hidden />}
          <span><strong>{item.kind === "render" ? item.scene : item.filename}</strong><small>{describe(item)}</small></span>
          <ArrowUpRight aria-hidden />
        </button>
      </li>)}</ol> : <p>New scripts and renders from MCP will appear here.</p>}
    </div>
  </section>;
}
