import { useId, type ReactNode } from "react";
import { Globe, HardDrive } from "lucide-react";

import { Section } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { QUALITY_OPTIONS } from "@/lib/constants";
import type { Quality, StorageMode } from "@/lib/types";
import { SidebarPanel } from "./SidebarPanel";

export interface Settings {
  storageMode: StorageMode;
  autoSave: boolean;
  downloadOnly: boolean;
  useOpenGL: boolean;
  loopPreview: boolean;
  editorFontSize: number;
  /** One render quality for every file (the toolbar's Quality picker changes the same setting). */
  quality: Quality;
}

interface SettingsPanelProps {
  settings: Settings;
  openGLSupported: boolean;
  onChange: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
}

function ToggleRow({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-3 px-1 py-1.5">
      <div className="min-w-0">
        <p id={`${id}-label`} className="text-xs font-medium text-fg">
          {label}
        </p>
        <p id={`${id}-description`} className="mt-0.5 text-2xs leading-relaxed text-fg-subtle">
          {description}
        </p>
      </div>
      <Switch
        checked={checked}
        disabled={disabled}
        onCheckedChange={onChange}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-description`}
        className="mt-0.5"
      />
    </div>
  );
}

export function SettingsPanel({ settings, openGLSupported, onChange }: SettingsPanelProps) {
  return (
    <SidebarPanel title="Settings">
      <div className="flex flex-col gap-5">
        <Section title="Scripts">
          <div className="flex flex-col gap-2 px-1">
            <Segmented
              aria-label="Where scripts are stored"
              value={settings.storageMode}
              onChange={(value) => onChange("storageMode", value)}
              options={[
                { value: "disk", label: <><HardDrive />Workspace</> },
                { value: "browser", label: <><Globe />Browser</> },
              ]}
            />
            <p className="text-2xs leading-relaxed text-fg-subtle">
              {settings.storageMode === "disk"
                ? "Scripts are files in the workspace folder next to the server."
                : "Scripts are kept in this browser's local storage and sent along with each render."}
            </p>
          </div>
        </Section>

        <Section title="Rendering">
          <div className="flex flex-col">
            <div className="flex items-start justify-between gap-3 px-1 py-1.5">
              <div className="min-w-0">
                <label htmlFor="render-quality" className="text-xs font-medium text-fg">
                  Render quality
                </label>
                <p id="render-quality-description" className="mt-0.5 text-2xs leading-relaxed text-fg-subtle">
                  Applies to all files. The Quality picker above the editor changes this same setting.
                </p>
              </div>
              <Select value={settings.quality} onValueChange={(value) => onChange("quality", value as Quality)}>
                <SelectTrigger id="render-quality" aria-describedby="render-quality-description" className="mt-0.5 w-[88px] shrink-0 gap-1 px-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="end">
                  {QUALITY_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label} · {option.detail.split(" · ")[0]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <ToggleRow
              label="Save before rendering"
              description="Write the editor to disk first. When off, the unsaved buffer is rendered and the file is left alone."
              checked={settings.autoSave}
              disabled={settings.storageMode === "browser"}
              onChange={(value) => onChange("autoSave", value)}
            />
            <ToggleRow
              label="Download-only mode"
              description="Send each render straight to your Downloads folder and delete it from the server."
              checked={settings.downloadOnly}
              onChange={(value) => onChange("downloadOnly", value)}
            />
            {openGLSupported && (
              <ToggleRow
                label="OpenGL renderer"
                description="Experimental. Faster for some 3D scenes, but not every Manim feature supports it."
                checked={settings.useOpenGL}
                onChange={(value) => onChange("useOpenGL", value)}
              />
            )}
          </div>
        </Section>

        <Section title="Editor & preview">
          <div className="flex flex-col">
            <div className="flex items-center justify-between gap-3 px-1 py-1.5">
              <label htmlFor="editor-font-size" className="text-xs font-medium text-fg">
                Editor font size
              </label>
              <Select value={String(settings.editorFontSize)} onValueChange={(value) => onChange("editorFontSize", Number(value))}>
                <SelectTrigger id="editor-font-size" className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[12, 13, 14, 15, 16, 18].map((size) => (
                    <SelectItem key={size} value={String(size)}>
                      {size}px
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <ToggleRow
              label="Loop preview"
              description="Replay videos in the preview pane continuously."
              checked={settings.loopPreview}
              onChange={(value) => onChange("loopPreview", value)}
            />
          </div>
        </Section>
      </div>
    </SidebarPanel>
  );
}
