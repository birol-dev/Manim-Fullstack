import { useEffect, useMemo, useState } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";
import { AlertTriangle, CornerDownLeft, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Callout, Section } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/tooltip";
import { pythonString } from "@/lib/format";
import { friendlyKatex } from "@/lib/katex";
import { LATEX_TEMPLATES } from "@/lib/templates";
import { cn } from "@/lib/utils";
import { SidebarPanel } from "./SidebarPanel";

function renderFormula(math: string, displayMode: boolean): { html: string; error: string | null } {
  try {
    return { html: katex.renderToString(math, { displayMode, throwOnError: true, strict: "ignore" }), error: null };
  } catch (err) {
    const message = err instanceof Error ? friendlyKatex(err.message) : "This formula couldn't be read. Check for a missing brace or symbol.";
    return { html: "", error: message };
  }
}

function Formula({ math, display = false, className }: { math: string; display?: boolean; className?: string }) {
  const { html, error } = useMemo(() => renderFormula(math, display), [math, display]);
  if (error) return <code className={cn("font-mono text-2xs text-fg-subtle", className)}>{math}</code>;
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Create the formula and show it, so an insert renders something. */
function mathTexSnippet(latex: string): string {
  return `tex = MathTex(${pythonString(latex.trim(), { raw: true })})\nself.play(Write(tex))`;
}

interface LatexPanelProps {
  latexAvailable: boolean;
  canInsert: boolean;
  onInsert: (code: string) => void;
  onOpenSetup: () => void;
}

let rememberedLatex = LATEX_TEMPLATES[0].code;

export function LatexPanel({ latexAvailable, canInsert, onInsert, onOpenSetup }: LatexPanelProps) {
  const [latex, setLatex] = useState(rememberedLatex);
  useEffect(() => {
    rememberedLatex = latex;
  }, [latex]);
  const preview = useMemo(() => renderFormula(latex, true), [latex]);

  return (
    <SidebarPanel title="LaTeX">
      <div className="flex flex-col gap-4">
        {!latexAvailable && (
          <Callout tone="warning" icon={<AlertTriangle />}>
            Rendering <code className="font-mono">MathTex</code> needs LaTeX on the server.{" "}
            <button type="button" onClick={onOpenSetup} className="font-medium text-fg underline-offset-2 hover:underline">
              Set it up
            </button>
            . This preview runs in your browser.
          </Callout>
        )}

        <Section title="Formula">
          <div className="flex flex-col gap-2 px-1">
            <Textarea
              aria-label="LaTeX formula"
              value={latex}
              onChange={(event) => setLatex(event.target.value)}
              rows={3}
              spellCheck={false}
              className="font-mono"
              placeholder="e^{i\pi} + 1 = 0"
            />
            <div
              aria-label="Formula preview"
              className="flex min-h-24 items-center justify-center overflow-auto rounded-lg border border-line bg-black px-3 py-4 text-[15px] text-white"
            >
              {!latex.trim() ? (
                <span className="text-xs text-fg-subtle">Type a formula to preview it</span>
              ) : preview.error ? (
                <span className="text-center font-mono text-2xs text-danger">{preview.error}</span>
              ) : (
                <span dangerouslySetInnerHTML={{ __html: preview.html }} />
              )}
            </div>
            <Button
              variant="primary"
              size="md"
              disabled={!canInsert || !latex.trim()}
              onClick={() => onInsert(mathTexSnippet(latex))}
            >
              <CornerDownLeft />
              Insert MathTex
            </Button>
          </div>
        </Section>

        <Section title="Examples">
          <ul className="flex flex-col gap-1">
            {LATEX_TEMPLATES.map((template) => (
              <li key={template.name} className="group flex items-center gap-1 rounded-md hover:bg-raised">
                <button
                  type="button"
                  onClick={() => setLatex(template.code)}
                  className="flex min-w-0 flex-1 flex-col items-start gap-1 overflow-hidden px-2 py-1.5 text-left"
                >
                  <span className="text-2xs text-fg-subtle">{template.name}</span>
                  <Formula math={template.code} className="max-w-full overflow-hidden text-[13px] text-fg" />
                </button>
                <Tooltip content={canInsert ? "Insert MathTex" : "Open a script to insert this formula"} wrap>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label={`Insert ${template.name}`}
                    disabled={!canInsert}
                    onClick={() => onInsert(mathTexSnippet(template.code))}
                    className="mr-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <Plus />
                  </Button>
                </Tooltip>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </SidebarPanel>
  );
}
