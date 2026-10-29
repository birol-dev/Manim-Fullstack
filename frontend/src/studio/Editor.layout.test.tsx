/** The desktop split from 900px: a one-row header and a compact format switcher. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { EditorPage } from "./Editor";
import { posterQueue } from "./hooks";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

// CSS imports are stubbed out in tests, so read the stylesheet itself.
const editorCss = readFileSync(resolve(process.cwd(), "src/studio/editor.css"), "utf8");

let studio: FakeStudio;
beforeEach(() => {
  posterQueue.clear();
  studio = installFakeStudio();
});

function open() {
  return render(
    <TooltipProvider>
      <EditorPage catalog={studio.catalog} route={{ kind: "new", template: "countdown", preset: "break-timer" }} onProjectCreated={() => {}} />
    </TooltipProvider>,
  );
}

/** The contents of the exact `@media <query>` block, found by matching braces. */
function mediaBlock(css: string, query: string) {
  const start = css.indexOf(`@media ${query} {`);
  expect(start).toBeGreaterThanOrEqual(0);
  const openBrace = css.indexOf("{", start);
  let depth = 0;
  for (let index = openBrace; index < css.length; index += 1) {
    if (css[index] === "{") depth += 1;
    else if (css[index] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(openBrace + 1, index);
    }
  }
  throw new Error(`Unclosed @media ${query}`);
}

it("fits the header on one row and keeps every format's full name available", () => {
  open();
  const header = document.querySelector<HTMLElement>(".studio-editor-header")!;
  expect(header.children).toHaveLength(3);
  const [identity, format, actions] = Array.from(header.children) as HTMLElement[];
  expect(identity).toHaveClass("studio-editor-identity");
  expect(actions).toHaveClass("studio-editor-actions");
  expect(screen.getByRole("radiogroup", { name: "Format" })).toBe(format);

  // The word ("Wide") is only hidden by CSS at laptop widths; the accessible name and the
  // hover tooltip keep it.
  const options = within(format).getAllByRole("radio");
  expect(options.map((option) => option.querySelector(".studio-format-label")?.textContent)).toEqual([
    "Wide",
    "Tall",
    "Square",
    "Portrait",
  ]);
  const wide = within(format).getByRole("radio", { name: /Wide\s*16:9/ });
  expect(wide).toHaveAttribute("title", "Wide 16:9: YouTube, TVs, slides");
  expect(wide.querySelector(".studio-format-label")).toHaveTextContent("Wide");
  expect(wide).toHaveTextContent("16:9");
});

it("splits from 900px with a narrow form column, leaving the height to the preview", () => {
  const desktop = mediaBlock(editorCss, "(min-width: 900px)");
  // Nothing scrolls the page: the editor clips and only the form column scrolls. The editor is
  // positioned so absolutely positioned content is contained by the clip instead of #root.
  expect(desktop).toMatch(/\.studio-editor\s*\{[^}]*position:\s*relative/);
  expect(desktop).toMatch(/\.studio-editor\s*\{[^}]*overflow:\s*hidden/);
  expect(desktop).toMatch(/\.studio-editor-body\s*\{[^}]*flex-direction:\s*row/);
  expect(desktop).toMatch(/\.studio-editor-body\s*\{[^}]*overflow:\s*hidden/);
  // The scrolling form column is the containing block for the form's absolutely positioned
  // sr-only inputs; otherwise they anchor to #root and grow the page past the window.
  expect(desktop).toMatch(/\.studio-editor-sidebar\s*\{[^}]*position:\s*relative/);
  expect(desktop).toMatch(/\.studio-editor-sidebar\s*\{[^}]*overflow-y:\s*auto/);
  expect(desktop).toMatch(/\.studio-editor-preview\s*\{[^}]*flex:\s*1 1 0/);
  expect(desktop).toMatch(/\.studio-editor-preview\s*\{[^}]*height:\s*auto/);
  expect(desktop).toMatch(/\.studio-editor-preview\s*\{[^}]*min-height:\s*0/);

  const laptop = mediaBlock(editorCss, "(min-width: 900px) and (max-width: 1199px)");
  const width = Number(/\.studio-editor-sidebar\s*\{[^}]*width:\s*(\d+)px/.exec(laptop)?.[1]);
  expect(width).toBeGreaterThanOrEqual(340);
  expect(width).toBeLessThanOrEqual(360);
  // A capped title ends in an ellipsis instead of a cut glyph.
  expect(laptop).toMatch(/\.studio-video-title\s*\{[^}]*max-width:\s*152px/);
  expect(laptop).toMatch(/\.studio-video-title\s*\{[^}]*text-overflow:\s*ellipsis/);
  expect(laptop).toMatch(/\.studio-editor-header\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) auto auto/);
  expect(laptop).toMatch(/\.studio-editor-identity\s*\{[^}]*grid-column:\s*auto/);
  expect(laptop).toMatch(/\.studio-title-group\s*\{[^}]*flex-wrap:\s*nowrap/);
  expect(laptop).toMatch(/\.studio-editor-preview\s*\{[^}]*padding:\s*14px 18px 18px/);
  expect(laptop).toMatch(/\.studio-format-label\s*\{[^}]*clip-path:\s*inset\(50%\)/);

  // The phone layout below 900 stays the one in studio.css: this file never stacks the editor.
  expect(editorCss).not.toMatch(/\.studio-editor-body\s*\{[^}]*flex-direction:\s*column/);
});

it("keeps the full video title in the input's tooltip when the column cuts it", () => {
  open();
  const title = screen.getByRole("textbox", { name: "Video title" });
  expect(title).toHaveValue("Countdown timer");
  expect(title).toHaveAttribute("title", "Countdown timer");
});
