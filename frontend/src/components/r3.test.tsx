import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";

import { BottomPanel } from "./console/BottomPanel";
import { ConsoleView } from "./console/ConsoleView";
import { TimelineView } from "./console/TimelineView";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Tooltip, TooltipProvider } from "./ui/tooltip";
import { STOPPING_MIN_DISPLAY_MS, useMinimumStopping } from "@/hooks/useMinimumStopping";
import type { LogEntry } from "@/hooks/useLogs";
import type { AnimationStep } from "@/lib/types";

afterEach(() => {
  vi.useRealTimers();
});

describe("useMinimumStopping (item 4)", () => {
  const render1 = { id: "r1" };

  it("keeps a quick cancel's 'Stopping…' on screen for the minimum time", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ active, stopping }) => useMinimumStopping(active, stopping), {
      initialProps: { active: render1 as { id: string } | null, stopping: false },
    });
    rerender({ active: render1, stopping: true });
    expect(result.current).toEqual({ active: render1, stopping: true });

    // The server confirms after 50 ms: the session is idle, the display lingers.
    act(() => vi.advanceTimersByTime(50));
    rerender({ active: null, stopping: false });
    expect(result.current).toEqual({ active: render1, stopping: true });

    act(() => vi.advanceTimersByTime(STOPPING_MIN_DISPLAY_MS - 50 - 1));
    expect(result.current.active).toBe(render1);
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toEqual({ active: null, stopping: false });
  });

  it("does not hold a stop that was already visible long enough", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ active, stopping }) => useMinimumStopping(active, stopping), {
      initialProps: { active: render1 as { id: string } | null, stopping: true },
    });
    act(() => vi.advanceTimersByTime(STOPPING_MIN_DISPLAY_MS + 10));
    rerender({ active: null, stopping: false });
    expect(result.current).toEqual({ active: null, stopping: false });
  });

  it("lets a new render replace the held one at once", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ active, stopping }) => useMinimumStopping(active, stopping), {
      initialProps: { active: render1 as { id: string } | null, stopping: true },
    });
    rerender({ active: null, stopping: false });
    expect(result.current.active).toBe(render1);
    const next = { id: "r2" };
    rerender({ active: next, stopping: false });
    expect(result.current).toEqual({ active: next, stopping: false });
    // After the hold expires the new render is still what's shown.
    act(() => vi.advanceTimersByTime(STOPPING_MIN_DISPLAY_MS));
    expect(result.current).toEqual({ active: next, stopping: false });
  });
});

describe("TimelineView keyboard (item 8)", () => {
  const steps: AnimationStep[] = [
    { type: "play", label: "Write(title)", line: 5, duration: 1, estimated: true },
    { type: "play", label: "Create(circle)", line: 6, duration: 1, estimated: true },
    { type: "wait", label: "Wait 0.5s", line: 7, duration: 0.5 },
  ];

  it("is one Tab stop with arrow, Home/End and Enter navigation", () => {
    const onJump = vi.fn();
    render(<TimelineView scene="Demo" steps={steps} activeIndex={null} onJumpToLine={onJump} />);
    const list = screen.getByRole("listbox", { name: "Animation steps in Demo" });
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(3);
    expect(options.map((option) => option.tabIndex)).toEqual([0, -1, -1]);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(options[0]).toHaveAccessibleName(/^Line 5: self\.play\(Write\(title\)\)/);

    act(() => options[0].focus());
    fireEvent.keyDown(list, { key: "ArrowRight" });
    expect(document.activeElement).toBe(options[1]);
    expect(screen.getAllByRole("option").map((option) => option.tabIndex)).toEqual([-1, 0, -1]);
    fireEvent.keyDown(list, { key: "End" });
    expect(document.activeElement).toBe(options[2]);
    fireEvent.keyDown(list, { key: "ArrowDown" });
    expect(document.activeElement).toBe(options[2]);
    fireEvent.keyDown(list, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(options[1]);
    fireEvent.keyDown(list, { key: "Home" });
    expect(document.activeElement).toBe(options[0]);
    fireEvent.keyDown(list, { key: "ArrowUp" });
    expect(document.activeElement).toBe(options[0]);

    fireEvent.keyDown(list, { key: "End" });
    fireEvent.keyDown(list, { key: "Enter" });
    expect(onJump).toHaveBeenLastCalledWith(7);
    fireEvent.click(options[1]);
    expect(onJump).toHaveBeenLastCalledWith(6);
  });

  it("starts at the step being rendered", () => {
    render(<TimelineView scene="Demo" steps={steps} activeIndex={1} onJumpToLine={() => {}} />);
    expect(screen.getAllByRole("option").map((option) => option.tabIndex)).toEqual([-1, 0, -1]);
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-current", "step");
  });
});

describe("ConsoleView copy (item 7)", () => {
  const logs: LogEntry[] = [
    "╭──── Traceback (most recent call last) ────╮",
    "│ /scene.py:7 in construct                  │",
    "│ ❱ 7 │   │   self.play(Transform(c, x))    │",
    "╰───────────────────────────────────────────╯",
    "NameError: name 'x' is not defined",
  ].map((text, index) => ({ id: index + 1, level: "stderr", text }));

  it("copies the selected traceback without the box border", () => {
    render(<ConsoleView logs={logs} linkFiles={["scene.py"]} onJumpToLine={() => {}} />);
    const log = screen.getByRole("log");
    const range = document.createRange();
    range.selectNodeContents(log);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    vi.spyOn(window.getSelection()!, "toString").mockReturnValue(logs.map((entry) => entry.text).join("\n"));
    const setData = vi.fn();
    fireEvent.copy(log, { clipboardData: { setData } });
    expect(setData).toHaveBeenCalledWith(
      "text/plain",
      ["Traceback (most recent call last)", "/scene.py:7 in construct", "❱ 7         self.play(Transform(c, x))", "NameError: name 'x' is not defined"].join(
        "\n",
      ),
    );
    window.getSelection()!.removeAllRanges();
  });
});

describe("BottomPanel 'Output from' chip (item 1)", () => {
  it("shows the other file's name in the header and opens it", () => {
    const onOpen = vi.fn();
    render(
      <TooltipProvider>
        <BottomPanel
          tab="console"
          onTabChange={() => {}}
          collapsed={false}
          onToggleCollapsed={() => {}}
          logs={[{ id: 1, level: "stdout", text: "hello" }]}
          linkFiles={[]}
          logsFile="qa_broken.py"
          onOpenLogsFile={onOpen}
          onClearLogs={() => {}}
          scene="Intro"
          steps={[]}
          activeStep={null}
          renderPercent={null}
          onJumpToLine={() => {}}
        />
      </TooltipProvider>,
    );
    const chip = screen.getByRole("note");
    expect(chip).toHaveAttribute("title", "Output from qa_broken.py, not the open file");
    // Not a row inside the log any more.
    expect(screen.getByRole("log")).not.toContainElement(chip);
    fireEvent.click(screen.getByRole("button", { name: "Open qa_broken.py" }));
    expect(onOpen).toHaveBeenCalledWith("qa_broken.py");
  });
});

describe("Tooltip and Select (item 6)", () => {
  it("doesn't reopen after a click until the pointer leaves (lingering Download tooltip)", async () => {
    render(
      <TooltipProvider delayDuration={0}>
        <Tooltip content="Download">
          <button type="button">dl</button>
        </Tooltip>
      </TooltipProvider>,
    );
    const button = screen.getByRole("button", { name: "dl" });
    fireEvent.pointerEnter(button);
    fireEvent.pointerMove(button);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Download");
    fireEvent.pointerDown(button);
    fireEvent.click(button);
    fireEvent.pointerMove(button);
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.pointerLeave(button);
    fireEvent.pointerEnter(button);
    fireEvent.pointerMove(button);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Download");
  });

  it("keeps the Select trigger's own data-state when wrapped in a tooltip", () => {
    render(
      <TooltipProvider>
        <Select value="m" onValueChange={() => {}}>
          <Tooltip content="Quality" wrap>
            <SelectTrigger aria-label="Quality">
              <SelectValue>720p</SelectValue>
            </SelectTrigger>
          </Tooltip>
          <SelectContent>
            <SelectItem value="m">720p</SelectItem>
          </SelectContent>
        </Select>
      </TooltipProvider>,
    );
    const trigger = screen.getByRole("combobox", { name: "Quality" });
    expect(trigger).toHaveAttribute("data-state", "closed");
    expect(trigger.parentElement?.tagName).toBe("SPAN");
  });
});
