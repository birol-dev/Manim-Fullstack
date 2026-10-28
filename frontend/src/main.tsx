import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";
import StudioApp from "./studio/StudioApp.tsx";

// The studio (gallery, editor, export) is the app; the code editor lives at #/author.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StudioApp />
  </StrictMode>,
);
