// Fix round 4: workspace entries that are symbolic links out of the workspace (or
// to nothing) are listed by /api/files with `outside`/`broken`; they can only be deleted.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FilesPanel } from "./FilesPanel";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { WorkspaceFiles } from "@/lib/types";

const files: WorkspaceFiles = {
  scripts: [
    { name: "ok.py", size: 10, type: "script" },
    { name: "out.py", size: 0, type: "script", outside: true },
    { name: "gone.py", size: 0, type: "script", broken: true },
  ],
  assets: [],
  media: [],
};

function setup() {
  const props = {
    files,
    filesError: false,
    storageMode: "disk" as const,
    activeFile: "ok.py",
    dirtyFiles: [],
    previewPath: null,
    onOpen: vi.fn(),
    onNew: vi.fn(),
    onRename: vi.fn(async () => {}),
    onDelete: vi.fn(),
    onRefresh: vi.fn(),
    onPreviewMedia: vi.fn(),
    onDeleteMedia: vi.fn(),
    onCompare: vi.fn(),
  };
  render(
    <TooltipProvider>
      <FilesPanel {...props} />
    </TooltipProvider>,
  );
  return props;
}

describe("link entries in the file list", () => {
  it("can't be opened or renamed, only deleted", async () => {
    const user = userEvent.setup();
    const props = setup();
    for (const [name, note] of [
      ["out.py", "link to a file outside the workspace"],
      ["gone.py", "broken link"],
    ]) {
      const row = screen.getByRole("button", {
        name: new RegExp(`^${name.replace(".", "\\.")}`),
      });
      expect(row).toHaveAttribute("aria-disabled", "true");
      // R4 visual: the reason is a real tooltip (shown on hover and focus) instead of a native title.
      expect(row).not.toHaveAttribute("title");
      expect(row.textContent).toBe(`${name} (${note}, can only be deleted)`);
      await user.hover(row);
      expect(
        (await screen.findAllByText(new RegExp(`^${note}: it can't be opened, only deleted\\.$`, "i")))[0],
      ).toBeInTheDocument();
      await user.unhover(row);
      await user.click(row);
      expect(props.onOpen).not.toHaveBeenCalled();
      expect(
        screen.queryByRole("button", { name: `Rename ${name}` }),
      ).toBeNull();
      await user.click(screen.getByRole("button", { name: `Delete ${name}` }));
      expect(props.onDelete).toHaveBeenLastCalledWith(name);
    }
  });

  it("leaves ordinary scripts as they were", async () => {
    const user = userEvent.setup();
    const props = setup();
    const row = screen.getByRole("button", { name: "ok.py" });
    expect(row).not.toHaveAttribute("aria-disabled");
    await user.click(row);
    expect(props.onOpen).toHaveBeenCalledWith("ok.py");
    expect(
      screen.getByRole("button", { name: "Rename ok.py" }),
    ).toBeInTheDocument();
  });
});
