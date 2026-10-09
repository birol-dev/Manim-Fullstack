import { forwardRef, lazy, Suspense, useEffect, useRef, useState } from "react";
import { AlertTriangle, FileCode2, FilePlus2, Loader2, Play, Save, Square, Zap } from "lucide-react";

import type { SyntaxErrorInfo } from "@/lib/types";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/panel";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import type { ActiveRender } from "@/hooks/useRenderSession";
import { MOD_KEY, QUALITY_OPTIONS } from "@/lib/constants";
import type { Quality } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { CodeEditorHandle } from "./types";

const CodeEditor = lazy(() => import("./CodeEditor"));

// Mobjects that are typeset with LaTeX under the hood.
const USES_LATEX =
  /\b(MathTex|Tex|SingleStringMathTex|BulletedList|Title|DecimalNumber|Integer|Variable|Matrix|MathTable)\s*\(|\badd_coordinates\s*\(|\binclude_numbers\s*=\s*True/;

// Select value for "Other scene…" (can't clash with a Python class name).
const OTHER_SCENE = " other";
const CLASS_NAME = /^[A-Za-z_]\w*$/;

/**
 * Scene picker. The list holds the scenes the parser can prove; "Other scene…"
 * lets you type any class name (aliased or factory-made bases, imported scenes).
 */
function ScenePicker({
  scenes,
  selectedScene,
  placeholder,
  disabled,
  onSceneChange,
}: {
  scenes: string[];
  selectedScene: string;
  placeholder: string;
  disabled: boolean;
  onSceneChange: (scene: string) => void;
}) {
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  // Enter/Escape in the name box hand focus back to the picker (a click elsewhere keeps it there).
  const triggerRef = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  useEffect(() => {
    if (typing || !refocus.current) return;
    refocus.current = false;
    triggerRef.current?.focus();
  }, [typing]);
  const typed = selectedScene && !scenes.includes(selectedScene) ? selectedScene : null;
  const valid = CLASS_NAME.test(draft.trim());
  // Sized to the scene name (no "CircleToS…" at 1024 px); the typed-name input gets the same box.
  const className = "w-auto min-w-[6.5rem] max-w-44 @max-[400px]:max-w-32 @max-[400px]:min-w-[5.5rem]";

  if (typing) {
    const commit = (keyboard = false) => {
      if (valid) onSceneChange(draft.trim());
      refocus.current = keyboard;
      setTyping(false);
    };
    return (
      <Input
        autoFocus
        aria-label="Scene class name"
        aria-invalid={draft.trim() !== "" && !valid ? true : undefined}
        title="Type the Scene class to render, then press Enter"
        placeholder="ClassName"
        value={draft}
        spellCheck={false}
        autoComplete="off"
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit(true);
          } else if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            refocus.current = true;
            setTyping(false);
          }
        }}
        onBlur={() => commit()}
        className={cn("h-7 w-36 font-mono text-xs @max-[400px]:w-28", className)}
      />
    );
  }

  return (
    <Select
      value={selectedScene}
      onValueChange={(value) => {
        if (value === OTHER_SCENE) {
          setDraft(typed ?? "");
          setTyping(true);
        } else {
          onSceneChange(value);
        }
      }}
      disabled={disabled}
    >
      <Tooltip content={selectedScene ? `Scene: ${selectedScene}` : "Scene to render (or type another with Other scene…)"} wrap>
        <SelectTrigger ref={triggerRef} aria-label="Scene" className={className}>
          <SelectValue placeholder={placeholder}>{selectedScene}</SelectValue>
        </SelectTrigger>
      </Tooltip>
      <SelectContent>
        {scenes.map((scene) => (
          <SelectItem key={scene} value={scene}>
            {scene}
          </SelectItem>
        ))}
        {typed && <SelectItem value={typed}>{typed}</SelectItem>}
        {(scenes.length > 0 || typed) && <SelectSeparator />}
        <SelectItem value={OTHER_SCENE}>Other scene…</SelectItem>
      </SelectContent>
    </Select>
  );
}

interface EditorPaneProps {
  storageKey: string;
  activeFile: string | null;
  code: string;
  isDirty: boolean;
  scenes: string[];
  selectedScene: string;
  quality: Quality;
  autoRender: boolean;
  /** This file's render (another file's job shows in the preview banner, not here). */
  active: ActiveRender | null;
  latexAvailable: boolean;
  canRender: boolean;
  /** Why Render won't run this buffer (size limit, syntax error): the button says so instead of rendering. */
  renderBlocked?: string | null;
  fontSize: number;
  syntaxError?: SyntaxErrorInfo | null;
  stopping?: boolean;
  onCodeChange: (code: string) => void;
  onCursorChange: (position: { line: number; column: number }) => void;
  onSceneChange: (scene: string) => void;
  onQualityChange: (quality: Quality) => void;
  onAutoRenderChange: (enabled: boolean) => void;
  onSave: () => void;
  onRender: () => void;
  onCancel: () => void;
  onNewFile: () => void;
  onOpenSetup: () => void;
}

export const EditorPane = forwardRef<CodeEditorHandle, EditorPaneProps>(function EditorPane(props, ref) {
  const { activeFile, code, isDirty, scenes, selectedScene, quality, active } = props;
  const rendering = active !== null;
  const qualityOption = QUALITY_OPTIONS.find((option) => option.value === quality);
  const needsLatexWarning = !props.latexAvailable && USES_LATEX.test(code);
  // Only when Render would otherwise be available (not while rendering, offline, ...).
  const blocked = props.canRender && props.renderBlocked ? props.renderBlocked : null;
  const oversize = props.renderBlocked && !props.syntaxError ? props.renderBlocked : null;

  return (
    <section aria-label="Editor" className="@container flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-surface">
      <div className="flex h-10 min-w-0 shrink-0 items-center gap-1.5 overflow-x-auto border-b border-line pl-1 pr-2">
        {activeFile && (
          <div className="flex h-full min-w-0 flex-1 items-center gap-2 overflow-hidden px-2 text-xs text-fg">
            <FileCode2 className="size-3.5 shrink-0 text-accent @max-[460px]:hidden" />
            <span className="min-w-[2.5rem] truncate font-medium" title={activeFile}>
              {activeFile}
            </span>
            {isDirty && <span className="size-1.5 shrink-0 rounded-full bg-fg-muted" aria-label="Unsaved changes" />}
          </div>
        )}

        <div className="flex shrink-0 items-center gap-1.5">
          <Tooltip
            content={!activeFile ? "Save (no script open)" : isDirty ? "Save" : "Saved (no unsaved changes)"}
            shortcut={`${MOD_KEY}+S`}
            wrap
          >
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Save"
              disabled={!activeFile || !isDirty}
              onClick={props.onSave}
              className="shrink-0"
            >
              <Save />
            </Button>
          </Tooltip>
          <Tooltip content={props.autoRender ? "Auto-render on (renders when you pause typing)" : "Auto-render when you pause typing"}>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Auto-render"
              aria-pressed={props.autoRender}
              onClick={() => props.onAutoRenderChange(!props.autoRender)}
              className={cn(props.autoRender && "bg-accent-soft text-accent hover:bg-accent-soft hover:text-accent")}
            >
              <Zap />
            </Button>
          </Tooltip>

          <ScenePicker
            key={activeFile ?? ""}
            scenes={scenes}
            selectedScene={selectedScene}
            disabled={!activeFile}
            placeholder={props.syntaxError ? `Syntax error, line ${props.syntaxError.line}` : activeFile ? "No scenes found" : "Scene"}
            onSceneChange={props.onSceneChange}
          />

          <Select value={quality} onValueChange={(value) => props.onQualityChange(value as Quality)}>
            {/* wrap: merged onto the trigger, the tooltip's data-state ("closed") would replace the Select's ("open"). */}
            <Tooltip content={qualityOption ? `Quality: ${qualityOption.label} · ${qualityOption.detail}` : "Render quality"} wrap>
              <SelectTrigger aria-label="Quality" className="w-[78px] shrink-0">
                <SelectValue>{qualityOption?.detail.split(" · ")[0]}</SelectValue>
              </SelectTrigger>
            </Tooltip>
            <SelectContent align="end">
              {QUALITY_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  <span className="flex w-36 items-center justify-between gap-3">
                    {option.label}
                    <span className="text-2xs text-fg-subtle">{option.detail}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {rendering ? (
            <Tooltip key="cancel" content={props.stopping ? "Stopping the render…" : "Cancel render"} wrap>
              <Button
                variant="secondary"
                size="sm"
                onClick={props.onCancel}
                disabled={props.stopping}
                className="w-[104px] @max-[520px]:w-auto"
                aria-label={props.stopping ? "Stopping" : "Cancel"}
              >
                <Square className="fill-current" />
                <span className="@max-[520px]:hidden">{props.stopping ? "Stopping…" : "Cancel"}</span>
              </Button>
            </Tooltip>
          ) : (
            <Tooltip key="render" content={blocked ?? "Render scene"} shortcut={blocked ? undefined : `${MOD_KEY}+Enter`} wrap>
              <Button
                variant="primary"
                size="sm"
                onClick={props.onRender}
                disabled={!props.canRender}
                // Still focusable when blocked, so the reason is reachable by keyboard and read out.
                aria-disabled={blocked ? true : undefined}
                aria-describedby={blocked ? "render-blocked-reason" : undefined}
                className={cn("w-[92px] @max-[520px]:w-auto", blocked && "cursor-not-allowed opacity-40 saturate-0 hover:brightness-100")}
                aria-label="Render"
              >
                <Play className="fill-current" />
                <span className="@max-[520px]:hidden">Render</span>
              </Button>
            </Tooltip>
          )}
          {blocked && (
            <span id="render-blocked-reason" className="sr-only">
              {blocked}
            </span>
          )}
        </div>
      </div>

      {props.syntaxError && (
        <div className="flex shrink-0 items-center gap-2 border-b border-danger/20 bg-danger-soft px-3 py-1.5 text-xs text-fg-muted">
          <AlertTriangle className="size-3.5 shrink-0 text-danger" />
          <span className="min-w-0 flex-1 truncate" title={props.syntaxError.message}>
            Line {props.syntaxError.line}: {props.syntaxError.message}
          </span>
        </div>
      )}

      {oversize && (
        <div
          role="note"
          className="flex shrink-0 items-center gap-2 border-b border-danger/20 bg-danger-soft px-3 py-1.5 text-xs text-fg-muted"
        >
          <AlertTriangle className="size-3.5 shrink-0 text-danger" />
          <span className="min-w-0 flex-1 truncate" title={oversize}>
            {oversize}
          </span>
        </div>
      )}

      {needsLatexWarning && (
        <div className="flex shrink-0 items-center gap-2 border-b border-warning/20 bg-warning-soft px-3 py-1.5 text-xs text-fg-muted">
          <AlertTriangle className="size-3.5 shrink-0 text-warning" />
          <span className="min-w-0 flex-1">This scene uses LaTeX (MathTex, Tex, numbers on axes…), which isn't installed.</span>
          <Button variant="ghost" size="xs" onClick={props.onOpenSetup} className="text-fg">
            Set up LaTeX
          </Button>
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        {activeFile ? (
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center gap-2 text-xs text-fg-subtle">
                <Loader2 className="size-4 animate-spin" /> Loading editor…
              </div>
            }
          >
            <CodeEditor
              ref={ref}
              path={`${props.storageKey}/${activeFile}`}
              value={code}
              fontSize={props.fontSize}
              onChange={props.onCodeChange}
              onCursorChange={props.onCursorChange}
              onSave={props.onSave}
              onRender={props.onRender}
              syntaxError={props.syntaxError ? { line: props.syntaxError.line, message: props.syntaxError.message } : null}
            />
          </Suspense>
        ) : (
          <EmptyState
            className="h-full"
            icon={<FileCode2 />}
            title="No script open"
            description="Pick a script from the Files panel or start a new one."
            action={
              <Button size="sm" onClick={props.onNewFile}>
                <FilePlus2 />
                New script
              </Button>
            }
          />
        )}
      </div>
    </section>
  );
});
