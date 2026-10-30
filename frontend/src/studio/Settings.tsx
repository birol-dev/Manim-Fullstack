import type { Appearance } from "./appearance";

export interface SettingsPageProps {
  section?: string;
  /** The app-level theme, so the appearance control can live here. */
  appearance?: Appearance;
  onAppearance?: (value: Appearance) => void;
}

/** Placeholder: the settings worker replaces this page's content. */
export function SettingsPage({ section }: SettingsPageProps) {
  const title = section === "ai" ? "Connect to AI" : "Settings";
  return (
    <div>
      <p className="studio-index-line">01</p>
      <h1 className="studio-display mt-6">{title}</h1>
      <p className="mt-4 max-w-md text-sm text-fg-muted">
        {section === "ai"
          ? "Connect Manim Studio to the AI assistant you already use."
          : "Choose how Manim Studio looks, where your files live, and how your AI assistant connects."}
      </p>
    </div>
  );
}
