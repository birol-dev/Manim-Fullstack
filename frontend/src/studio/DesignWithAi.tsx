import { useId, useState } from "react";
import { Check, Copy, Save, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SaveStatus } from "./autosave";

interface DesignWithAiProps {
  projectId: string | null;
  templateId: string;
  direction: string;
  onDirectionChange: (direction: string) => void;
  saveStatus: SaveStatus;
  conflict: boolean;
  onSave: () => void;
}

function designBrief(projectId: string, templateId: string, direction: string) {
  return [
    "Work with me on the video I have open in Manim Studio.",
    `Project ID ${projectId}`,
    `Template ${templateId}`,
    "Use the Manim Studio MCP. Read get_project and get_template first, then guide(\"look\") for the visual choices.",
    "Use the current project revision as base_revision when calling update_project. Keep the fields my brief leaves alone. If a save conflicts, read the project again before making another change.",
    "Preview the storyboard for readability, then leave the result in this project so I can review and edit it in Studio.",
    direction.trim() ? `My design direction\n${direction.trim()}` : "Add your design direction here.",
  ].join("\n\n");
}

export function DesignWithAi({ projectId, templateId, direction, onDirectionChange, saveStatus, conflict, onSave }: DesignWithAiProps) {
  const directionId = useId();
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const saving = saveStatus === "pending" || saveStatus === "saving";
  const brief = projectId && !saving && !conflict && saveStatus !== "error" ? designBrief(projectId, templateId, direction) : null;

  const copy = async () => {
    if (!brief) return;
    try {
      await navigator.clipboard.writeText(brief);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  return <section className="studio-ai-design">
    <p className="studio-ai-eyebrow"><Sparkles aria-hidden /> Shared project</p>
    <h2>Design together</h2>
    <p className="studio-ai-intro">Give your connected AI app a direction for this draft. Keep this editor open to see its saved changes in the preview.</p>

    <div className="studio-ai-brief-card">
      <label htmlFor={directionId}>What should the agent change?</label>
      <textarea id={directionId} value={direction} maxLength={1200} rows={4}
        placeholder="Try a dark editorial look with a pale yellow accent. Keep my headline."
        onChange={(event) => { setCopyState("idle"); onDirectionChange(event.target.value); }} />
      {brief ? <>
        <Button variant="primary" size="md" className="w-full" onClick={() => void copy()}>
          {copyState === "copied" ? <Check /> : <Copy />}
          {copyState === "copied" ? "Copied" : "Copy design brief"}
        </Button>
        <p role="status" className="studio-ai-small">{copyState === "copied" ? "Paste the brief into your connected AI app." : copyState === "failed" ? "Copy the brief below." : "Includes this project's ID and editing instructions."}</p>
        <details open={copyState === "failed" || undefined}>
          <summary>View brief</summary>
          <pre tabIndex={0} aria-label="Design brief">{brief}</pre>
        </details>
      </> : conflict ? (
        <p role="status" className="studio-ai-small">Load the newest version above to share the current draft.</p>
      ) : <>
        <Button variant="primary" size="md" className="w-full" disabled={saving} onClick={onSave}>
          <Save /> {saving ? "Saving draft…" : "Save draft to share"}
        </Button>
        <p className="studio-ai-small">{saveStatus === "error" ? "Try saving again to make the current draft available." : "A saved draft gives both of you the same project to edit."}</p>
      </>}
    </div>
    <p className="studio-ai-small">Connect an assistant from <strong>Settings → AI apps</strong>. Saved changes appear here when your edits finish saving.</p>
  </section>;
}
