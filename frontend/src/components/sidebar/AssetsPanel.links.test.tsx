// Assets that are symbolic links out of the assets folder (or to nothing) are listed by
// /api/files with `outside`/`broken` and no URL; they can only be deleted.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AssetsPanel } from "./AssetsPanel";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { AssetFile } from "@/lib/types";

const assets: AssetFile[] = [
  { name: "ok.png", size: 2048, type: "asset", url: "/assets/ok.png" },
  { name: "out.png", size: 0, type: "asset", url: "", outside: true },
  { name: "gone.png", size: 0, type: "asset", url: "", broken: true },
];

function setup() {
  const props = { assets, canInsert: true, onUpload: vi.fn(async () => {}), onInsert: vi.fn(), onDelete: vi.fn() };
  render(
    <TooltipProvider>
      <AssetsPanel {...props} />
    </TooltipProvider>,
  );
  return props;
}

describe("link entries in the assets library", () => {
  it("offer Delete only, and never load the link as an image", async () => {
    const user = userEvent.setup();
    const props = setup();
    // Only the regular asset gets a thumbnail.
    expect(document.querySelectorAll("img")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Insert ok.png" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy path of ok.png" })).toBeInTheDocument();
    for (const [name, note] of [
      ["out.png", "link to a file outside the assets folder"],
      ["gone.png", "broken link"],
    ]) {
      expect(screen.queryByRole("button", { name: `Insert ${name}` })).toBeNull();
      expect(screen.queryByRole("button", { name: `Copy path of ${name}` })).toBeNull();
      expect(screen.getByText(`(${note}, can only be deleted)`, { exact: false })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: `Delete ${name}` }));
      expect(props.onDelete).toHaveBeenLastCalledWith(expect.objectContaining({ name }));
    }
    expect(screen.getByText("Link")).toBeInTheDocument();
    expect(screen.getByText("Broken link")).toBeInTheDocument();
  });
});
