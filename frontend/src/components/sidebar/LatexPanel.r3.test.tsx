// Fix round 3: KaTeX 0.19. The preview still renders formulas, and parse errors
// (e.g. "Unexpected end of input") still become the friendly hints.
import { fireEvent, render, screen } from "@testing-library/react";
import katex from "katex";
import { describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { friendlyKatex } from "@/lib/katex";
import { LatexPanel } from "./LatexPanel";

function renderPanel() {
  render(
    <TooltipProvider>
      <LatexPanel latexAvailable canInsert onInsert={vi.fn()} onOpenSetup={vi.fn()} />
    </TooltipProvider>,
  );
  return screen.getByLabelText("LaTeX formula");
}

describe("KaTeX 0.19", () => {
  it("is the version in use", () => {
    expect(katex.version.startsWith("0.19.")).toBe(true);
  });

  it("renders a formula to HTML and MathML", () => {
    const html = katex.renderToString("\\frac{a}{b} + e^{i\\pi}", { displayMode: true, throwOnError: true, strict: "ignore" });
    expect(html).toContain('class="katex-display"');
    expect(html).toContain("<math");
    expect(html).toContain("mfrac");
  });

  it("still throws ParseError with the 'Unexpected end of input' wording", () => {
    let message = "";
    try {
      katex.renderToString("\\frac{a", { displayMode: true, throwOnError: true, strict: "ignore" });
    } catch (error) {
      expect(error).toBeInstanceOf(katex.ParseError);
      message = (error as Error).message;
    }
    expect(message).toMatch(/Unexpected end of input/);
    expect(friendlyKatex(message)).toBe("Missing closing brace '}': a { … } group isn't closed.");
  });

  it("does not report missing font metrics for ordinary Unicode in the preview (strict: ignore)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(() => katex.renderToString("x ≤ y → z", { throwOnError: true, strict: "ignore" })).not.toThrow();
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe("LatexPanel preview", () => {
  it("renders the typed formula with KaTeX", () => {
    const input = renderPanel();
    fireEvent.change(input, { target: { value: "\\sqrt{x^2 + 1}" } });
    const preview = screen.getByLabelText("Formula preview");
    expect(preview.querySelector(".katex")).not.toBeNull();
    expect(preview.querySelector(".katex .sqrt")).not.toBeNull();
  });

  it("shows the friendly hint for an unclosed brace", () => {
    const input = renderPanel();
    fireEvent.change(input, { target: { value: "\\frac{a" } });
    const preview = screen.getByLabelText("Formula preview");
    expect(preview).toHaveTextContent("Missing closing brace '}'");
    expect(preview.querySelector(".katex")).toBeNull();
  });
});
