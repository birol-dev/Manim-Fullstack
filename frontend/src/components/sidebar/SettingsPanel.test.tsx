import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsPanel, type Settings } from "./SettingsPanel";
import { TooltipProvider } from "@/components/ui/tooltip";

const SETTINGS: Settings = {
  storageMode: "disk",
  autoSave: true,
  downloadOnly: false,
  useOpenGL: false,
  loopPreview: true,
  editorFontSize: 13,
  quality: "m",
};

describe("SettingsPanel render quality", () => {
  it.each([
    ["l", "Low"],
    ["m", "Medium"],
    ["h", "High"],
    ["k", "4K"],
  ] as const)("shows the %s level by name only, so it fits its 88 px select", (quality, label) => {
    render(
      <TooltipProvider>
        <SettingsPanel settings={{ ...SETTINGS, quality }} openGLSupported={false} onChange={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.getByRole("combobox", { name: "Render quality" })).toHaveTextContent(new RegExp(`^${label}$`));
  });
});
