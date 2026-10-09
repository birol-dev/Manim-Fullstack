import { forwardRef, lazy, Suspense } from "react";
import { AlertTriangle, FileCode2, FilePlus2, Loader2, Play, Save, Square, Zap } from "lucide-react";

import type { SyntaxErrorInfo } from "@/lib/types";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/panel";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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

interface EditorPaneProps {
  storageKey: string;
  activeFile: string | null;
  code: string;
  isDirty: boolean;
  scenes: string[];
  selectedScene: string;
  quality: Quality;
  autoRender: boolean;
  active: ActiveRender | null;
  latexAvailable: boolean;
  canRender: boolean;
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

  return (
    <section aria-label="Editor" className="@container flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-surface">
      <div className="flex h-10 min-w-0 shrink-0 items-center gap-1.5 overflow-x-auto border-b border-line pl-1 pr-2">
        {activeFile && (
          <div className="flex h-full min-w-0 flex-1 items-center gap-2 overflow-hidden px-2 text-xs text-fg">
            <FileCode2 className="size-3.5 shrink-0 text-accent" />
            <span className="min-w-0 truncate font-medium" title={activeFile}>
              {activeFile}
            </span>
            {isDirty && <span className="size-1.5 shrink-0 rounded-full bg-fg-muted" aria-label="Unsaved changes" />}
          </div>
        )}

        <div className="flex shrink-0 items-center gap-1.5">
          <Tooltip content="Save" shortcut={`${MOD_KEY}+S`}>
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

          <Select value={selectedScene} onValueChange={props.onSceneChange} disabled={scenes.length === 0}>
            <SelectTrigger aria-label="Scene" className="w-36 min-w-0 @max-[720px]:w-28 @max-[420px]:w-24">
              <SelectValue
                placeholder={
                  props.syntaxError ? `Syntax error, line ${props.syntaxError.line}` : activeFile ? "No scenes found" : "Scene"
                }
              />
            </SelectTrigger>
            <SelectContent>
              {scenes.map((scene) => (
                <SelectItem key={scene} value={scene}>
                  {scene}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={quality} onValueChange={(value) => props.onQualityChange(value as Quality)}>
            <SelectTrigger aria-label="Quality" className="w-[88px] @max-[420px]:w-16">
              <SelectValue>{qualityOption?.detail.split(" · ")[0]}</SelectValue>
            </SelectTrigger>
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
          ) : (
            <Tooltip content="Render scene" shortcut={`${MOD_KEY}+Enter`}>
              <Button
                variant="primary"
                size="sm"
                onClick={props.onRender}
                disabled={!props.canRender}
                className="w-[92px] @max-[520px]:w-auto"
                aria-label="Render"
              >
                <Play className="fill-current" />
                <span className="@max-[520px]:hidden">Render</span>
              </Button>
            </Tooltip>
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
