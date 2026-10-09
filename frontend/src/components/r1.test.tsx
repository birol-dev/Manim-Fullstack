import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ConsoleView } from "./console/ConsoleView";
import { TimelineView } from "./console/TimelineView";
import { ActivityBar } from "./layout/ActivityBar";
import { Tooltip, TooltipProvider } from "./ui/tooltip";
import type { LogEntry } from "@/hooks/useLogs";

const TRACEBACK: LogEntry[] = [
  "╭─────────── Traceback (most recent call last) ───────────╮",
  "│ /venv/lib/python3.13/site-packages/manim/scene/scene.py:320 in render │",
  "│ ❱  320 │   │   return self._get_manager().render(preview)        │",
  "│                                                                  │",
  "│ /scene.py:7 in construct                                         │",
  "│   6 │   │   self.play(Create(c))                                 │",
  "│ ❱ 7 │   │   self.play(Transform(c, undefined_name))              │",
  "╰──────────────────────────────────────────────────────────────────╯",
  "NameError: name 'undefined_name' is not defined",
].map((text, index) => ({ id: index + 1, level: "stderr", text }));

describe("ConsoleView traceback", () => {
  it("hides library frames behind an expandable row", async () => {
    render(<ConsoleView logs={TRACEBACK} linkFiles={["scene.py"]} onJumpToLine={() => {}} />);
    expect(screen.queryByText(/site-packages/)).toBeNull();
    const toggle = screen.getByRole("button", { name: /1 library frame hidden/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(screen.getByText(/site-packages/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hide 1 library frame/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/^NameError/)).toBeInTheDocument();
  });

  it("jumps from the user's code lines, not only the header", async () => {
    const onJump = vi.fn();
    render(<ConsoleView logs={TRACEBACK} linkFiles={["scene.py"]} onJumpToLine={onJump} />);
    await userEvent.click(screen.getByText(/self\.play\(Create\(c\)\)/));
    expect(onJump).toHaveBeenLastCalledWith(6);
    await userEvent.click(screen.getByText(/self\.play\(Transform/));
    expect(onJump).toHaveBeenLastCalledWith(7);
    await userEvent.click(screen.getByText("scene.py:7"));
    expect(onJump).toHaveBeenLastCalledWith(7);
    // Keyboard / screen-reader control lives on the frame header only.
    expect(screen.getAllByRole("button", { name: /^Go to line/ }).map((button) => button.getAttribute("aria-label"))).toEqual([
      "Go to line 7",
    ]);
  });
});

describe("TimelineView", () => {
  it("shows loop badges, estimated durations and the total with repeats", () => {
    render(
      <TimelineView
        scene="Loopy"
        activeIndex={null}
        onJumpToLine={() => {}}
        steps={[
          { type: "play", label: "Write(title), Create(circle)", line: 6, duration: 2, estimated: true },
          { type: "play", label: "Indicate(dot)", line: 8, duration: 1, estimated: true, repeat: 3, loop_line: 7 },
          { type: "wait", label: "Wait 0.5s", line: 9, duration: 0.5 },
        ]}
      />,
    );
    expect(screen.getByText(/3 steps/)).toHaveTextContent("Loopy · 3 steps (1 in a loop, 5 plays) · ≈ 5.5s");
    expect(screen.getByLabelText("Repeats 3 times")).toHaveTextContent("×3");
    // Line breaks are offered between tokens via <wbr>, never inside "title".
    const label = screen.getByText((_, element) => element?.textContent === "Write(title), Create(circle)" && element.tagName === "SPAN");
    expect(label.querySelectorAll("wbr").length).toBe(3);
    expect(label).toHaveClass("code-wrap");
  });
});

describe("ActivityBar", () => {
  it("keeps the accent bar on the selected view while the sidebar is collapsed", () => {
    const { rerender } = render(
      <TooltipProvider>
        <ActivityBar view="templates" open onSelect={() => {}} />
      </TooltipProvider>,
    );
    expect(screen.getByTestId("accent-templates")).not.toHaveClass("opacity-50");
    rerender(
      <TooltipProvider>
        <ActivityBar view="templates" open={false} onSelect={() => {}} />
      </TooltipProvider>,
    );
    expect(screen.getByTestId("accent-templates")).toHaveClass("opacity-50");
    expect(screen.getByRole("button", { name: "Templates" })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("Tooltip", () => {
  function setup() {
    return render(
      <TooltipProvider delayDuration={0}>
        <Tooltip content="Open in new tab">
          <button type="button">open</button>
        </Tooltip>
        <Tooltip content="Save" wrap>
          <button type="button" disabled>
            save
          </button>
        </Tooltip>
      </TooltipProvider>,
    );
  }

  it("does not open when focus returns without the keyboard (ghost tooltip)", () => {
    setup();
    fireEvent.pointerDown(window);
    act(() => screen.getByRole("button", { name: "open" }).focus());
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("does not open when focus moves after a non-Tab key (Escape restoring focus)", () => {
    setup();
    fireEvent.keyDown(window, { key: "Escape" });
    act(() => screen.getByRole("button", { name: "open" }).focus());
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("opens on Tab focus and closes on blur", async () => {
    setup();
    fireEvent.keyDown(window, { key: "Tab" });
    act(() => screen.getByRole("button", { name: "open" }).focus());
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Open in new tab");
    act(() => screen.getByRole("button", { name: "open" }).blur());
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("wraps disabled triggers so they can still be hovered", () => {
    setup();
    const wrapper = screen.getByRole("button", { name: "save" }).parentElement!;
    expect(wrapper.tagName).toBe("SPAN");
    expect(wrapper).toHaveAttribute("data-state");
  });
});
