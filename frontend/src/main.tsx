import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/newsreader";
import "./index.css";
import { loadPreferences } from "./studio/preferences.ts";
import StudioApp from "./studio/StudioApp.tsx";

// The desktop app's WebView starts with empty browser storage at every launch, so the
// theme, sidebar and category choices are restored from the workspace before the first
// paint (waiting briefly, so an unreachable server can't hold the app back).
await loadPreferences();

// The studio (gallery, editor, export) is the app; the code editor lives at #/author.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StudioApp />
  </StrictMode>,
);
