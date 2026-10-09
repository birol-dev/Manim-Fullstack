// Fix round 4 (visual): component behaviour behind the tooltip, timeline, console and focus fixes.
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";

import { BottomPanel } from "./console/BottomPanel";
import { TimelineView } from "./console/TimelineView";
import { LatexPanel } from "./sidebar/LatexPanel";
import { Tooltip, TooltipProvider } from "./ui/tooltip";
import { STOPPING_MIN_DISPLAY_MS, useMinimumStopping } from "@/hooks/useMinimumStopping";
import type { LogEntry } from "@/hooks/useLogs";
import type { AnimationStep } from "@/lib/types";

afterEach(() => {
  vi.useRealTimers();
});

const steps: AnimationStep[] = [
  { type: "play", label: "Write(title)", line: 5, duration: 1, estimated: true },
  { type: "play", label: "Create(circle)", line: 6, duration: 1, estimated: true },
  { type: "wait", label: "Wait 0.5s", line: 7, duration: 0.5 },
];

function panel(overrides: Partial<React.ComponentProps<typeof BottomPanel>> = {}) {
  return (
    <TooltipProvider>
      <BottomPanel
        tab="console"
        onTabChange={() => {}}
        collapsed={false}
        onToggleCollapsed={() => {}}
        logs={[]}
        linkFiles={[]}
        logsFile={null}
        onOpenLogsFile={() => {}}
        onClearLogs={() => {}}
        scene="Demo"
        steps={steps}
        activeStep={null}
        renderPercent={null}
        onJumpToLine={() => {}}
        {...overrides}
      />
    </TooltipProvider>
  );
}

describe("tooltips close when the pointer has gone (item 7)", () => {
  it("closes a hover-opened hint on a pointer move outside its trigger, even without pointerleave", () => {
    vi.useFakeTimers();
    render(
      <TooltipProvider delayDuration={0}>
        <Tooltip content="Rendering SlowScene from qa_slow.py" wrap>
          <button type="button" aria-disabled="true">
            Render
          </button>
        </Tooltip>
        <div data-testid="elsewhere">editor</div>
      </TooltipProvider>,
    );
    const trigger = screen.getByRole("button", { name: "Render" }).parentElement!;
    fireEvent.pointerEnter(trigger);
    fireEvent.pointerMove(trigger);
    act(() => vi.advanceTimersByTime(50));
    expect(screen.getAllByText("Rendering SlowScene from qa_slow.py").length).toBeGreaterThan(0);
    // No pointerleave (the missed event): a move over the editor still closes it.
    fireEvent.pointerMove(screen.getByTestId("elsewhere"), { clientX: 900, clientY: 500 });
    act(() => vi.advanceTimersByTime(300));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});

describe("disabled LaTeX Insert explains itself (item 10)", () => {
  it("wraps the disabled button so hovering shows why", () => {
    vi.useFakeTimers();
    render(
      <TooltipProvider delayDuration={0}>
        <LatexPanel latexAvailable canInsert={false} onInsert={() => {}} onOpenSetup={() => {}} />
      </TooltipProvider>,
    );
    // (getByRole computes names through KaTeX markup, which jsdom can't style.)
    const insert = screen.getByText("Insert MathTex").closest("button")!;
    expect(insert).toBeDisabled();
    const wrapper = insert.parentElement!;
    expect(wrapper.tagName).toBe("SPAN");
    fireEvent.pointerEnter(wrapper);
    fireEvent.pointerMove(wrapper);
    act(() => vi.advanceTimersByTime(50));
    expect(screen.getAllByText("Open a script to insert this formula").length).toBeGreaterThan(0);
  });
});

describe("timeline focus and Tab stops (item 4, extra b)", () => {
  it("the timeline tab panel is not a Tab stop of its own", () => {
    render(panel({ tab: "timeline" }));
    const tabpanel = screen.getByRole("tabpanel");
    expect(tabpanel).toHaveAttribute("tabindex", "-1");
    // The step list stays one Tab stop.
    expect(screen.getAllByRole("option").filter((option) => option.tabIndex === 0)).toHaveLength(1);
  });

  it("forgets the focused card when another file opens", () => {
    const { rerender } = render(panel({ tab: "timeline", timelineKey: "a.py" }));
    const list = screen.getByRole("listbox");
    screen.getAllByRole("option")[0].focus();
    fireEvent.keyDown(list, { key: "End" });
    expect(screen.getAllByRole("option")[2]).toHaveAttribute("tabindex", "0");
    rerender(panel({ tab: "timeline", timelineKey: "b.py" }));
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("tabindex", "0");
    expect(screen.getAllByRole("option")[2]).toHaveAttribute("tabindex", "-1");
  });

  it("keeps it for the same file", () => {
    const { rerender } = render(<TimelineView key="a.py" scene="Demo" steps={steps} activeIndex={null} onJumpToLine={() => {}} />);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "End" });
    rerender(<TimelineView key="a.py" scene="Demo" steps={steps} activeIndex={null} onJumpToLine={() => {}} />);
    expect(screen.getAllByRole("option")[2]).toHaveAttribute("tabindex", "0");
  });
});

describe("console queued line follows the live position (item 3)", () => {
  const logs: LogEntry[] = [
    { id: 1, level: "command", text: "$ manim qa_visual.py CircleToSquare -qm" },
    { id: 2, level: "info", text: "Waiting for another render to finish… (position 2 in queue)" },
  ];

  it("updates while queued and keeps the last position once the render starts", () => {
    const { rerender } = render(panel({ logs, queuePosition: 2 }));
    expect(screen.getByText("Waiting for another render to finish… (position 2 in queue)")).toBeInTheDocument();
    rerender(panel({ logs, queuePosition: 1 }));
    expect(screen.getByText("Waiting for another render to finish… (position 1 in queue)")).toBeInTheDocument();
    expect(screen.queryByText(/position 2 in queue/)).toBeNull();
    // Started: no live position any more, the line keeps "position 1".
    rerender(panel({ logs, queuePosition: null }));
    expect(screen.getByText("Waiting for another render to finish… (position 1 in queue)")).toBeInTheDocument();
    // Switching to the timeline and back doesn't lose it.
    rerender(panel({ logs, queuePosition: null, tab: "timeline" }));
    rerender(panel({ logs, queuePosition: null, tab: "console" }));
    expect(screen.getByText("Waiting for another render to finish… (position 1 in queue)")).toBeInTheDocument();
  });
});

describe("console Copy button (extra a)", () => {
  it("is a labelled, focusable button that copies the plain text", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const logs: LogEntry[] = [
      { id: 1, level: "stderr", text: "╭──── Traceback (most recent call last) ────╮" },
      { id: 2, level: "stderr", text: "│ ❱ 7 │   │   self.play(Transform(c, x))    │" },
      { id: 3, level: "stderr", text: "╰───────────────────────────────────────────╯" },
      { id: 4, level: "error", text: "NameError: name 'x' is not defined" },
    ];
    render(panel({ logs }));
    const copy = screen.getByRole("button", { name: "Copy console output" });
    copy.focus();
    expect(copy).toHaveFocus();
    await act(async () => {
      fireEvent.click(copy);
    });
    expect(writeText).toHaveBeenCalledTimes(1);
    const text = writeText.mock.calls[0][0] as string;
    expect(text.split("\n")[0]).toBe("Traceback (most recent call last)");
    expect(text).toContain("❱ 7         self.play(Transform(c, x))");
    expect(text).not.toMatch(/[│╭╮╰╯─]/);
  });

  it("is not shown for an empty console", () => {
    render(panel({ logs: [] }));
    expect(screen.queryByRole("button", { name: "Copy console output" })).toBeNull();
  });
});

describe("useMinimumStopping does not re-flash (extra c)", () => {
  it("drops the held 'Stopping…' for good once another render takes over", () => {
    vi.useFakeTimers();
    const first = { id: "r1" };
    const second = { id: "r2" };
    const { result, rerender } = renderHook(({ active, stopping }) => useMinimumStopping(active, stopping), {
      initialProps: { active: first as { id: string } | null, stopping: false },
    });
    rerender({ active: first, stopping: true });
    act(() => vi.advanceTimersByTime(20));
    rerender({ active: null, stopping: false });
    expect(result.current).toEqual({ active: first, stopping: true });
    // A quick re-render starts inside the hold window...
    rerender({ active: second, stopping: false });
    expect(result.current).toEqual({ active: second, stopping: false });
    // ...and finishes inside it too: the old "Stopping…" must not come back.
    act(() => vi.advanceTimersByTime(20));
    rerender({ active: null, stopping: false });
    expect(result.current).toEqual({ active: null, stopping: false });
    act(() => vi.advanceTimersByTime(STOPPING_MIN_DISPLAY_MS));
    expect(result.current).toEqual({ active: null, stopping: false });
  });
});
