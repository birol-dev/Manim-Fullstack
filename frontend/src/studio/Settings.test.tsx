import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetCatalogCache } from "./api";
import { BRAND_NAME_KEY, DEFAULT_FORMAT_KEY, resetPreferencesForTests } from "./preferences";
import { SettingsPage } from "./Settings";
import { type AIApp, type SetupComponent, type SetupStatus } from "./setup";
import StudioApp from "./StudioApp";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

let studio: FakeStudio;

function app(overrides: Partial<AIApp> = {}): AIApp {
  return {
    id: "claude-desktop",
    label: "Claude Desktop",
    detected: true,
    connected: false,
    needs_repair: false,
    restart_hint: null,
    error: null,
    ...overrides,
  };
}

function component(overrides: Partial<SetupComponent> = {}): SetupComponent {
  return {
    id: "renderer",
    label: "Video renderer",
    purpose: "Draws every video.",
    status: "ready",
    required: true,
    can_install: false,
    detail: "Manim 0.18 is ready.",
    progress: null,
    ...overrides,
  };
}

function setupStatus(overrides: Partial<SetupStatus> = {}): SetupStatus {
  return {
    platform: "windows",
    mode: "desktop",
    components: [component()],
    ai_apps: [app()],
    data_folder: String.raw`C:\Users\Omer\AppData\Roaming\Manim Studio`,
    ...overrides,
  };
}

function servePreferences() {
  const previous = studio.reply;
  studio.reply = (call) => call.path === "/api/studio/preferences" && call.method === "PATCH"
    ? { status: 200, body: { ...(call.body as object) } }
    : previous?.(call) ?? null;
}

beforeEach(() => {
  resetPreferencesForTests();
  resetCatalogCache();
  window.history.replaceState(null, "", "/#/");
  studio = installFakeStudio();
});

describe("settings sections", () => {
  it("puts every section in the menu as a real link and marks the current one", () => {
    render(<SettingsPage section="defaults" />);
    const nav = screen.getByRole("navigation", { name: "Settings" });
    for (const [label, href] of [
      ["You", "#/settings/profile"],
      ["New videos", "#/settings/defaults"],
      ["Appearance", "#/settings/appearance"],
      ["AI assistants", "#/settings/ai"],
      ["This computer", "#/settings/system"],
      ["About", "#/settings/about"],
    ]) {
      expect(within(nav).getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
    expect(within(nav).getByRole("link", { name: "New videos" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "You" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("heading", { name: "New videos" })).toBeInTheDocument();
  });

  it("falls back to You for an unknown section and follows the address bar", async () => {
    render(<SettingsPage section="nope" />);
    expect(screen.getByRole("link", { name: "You" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "You" })).toBeInTheDocument();

    cleanup();
    window.history.replaceState(null, "", "/#/settings/appearance");
    render(<StudioApp />);
    expect(await screen.findByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
    const nav = await screen.findByRole("navigation", { name: "Settings" });
    expect(within(nav).getByRole("link", { name: "Appearance" })).toHaveAttribute("aria-current", "page");
  });

  it("applies the appearance at once and offers no save button", async () => {
    const user = userEvent.setup();
    const onAppearance = vi.fn();
    render(<SettingsPage section="appearance" appearance="light" onAppearance={onAppearance} />);
    const group = screen.getByRole("radiogroup", { name: "Theme" });
    expect(within(group).getByRole("radio", { name: "Light" })).toHaveAttribute("aria-checked", "true");
    await user.click(within(group).getByRole("radio", { name: "Dark" }));
    expect(onAppearance).toHaveBeenCalledWith("dark");
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  });
});

describe("profile and new videos", () => {
  it("saves the name and brand colour only when something changed", async () => {
    const user = userEvent.setup();
    servePreferences();
    localStorage.setItem(BRAND_NAME_KEY, "Acme");
    render(<SettingsPage section="profile" />);

    const name = screen.getByRole("textbox", { name: "What should we call you?" });
    expect(name).toHaveValue("Acme");
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.getByText("New videos start with this colour. You can change it per video.")).toBeInTheDocument();

    await user.clear(name);
    await user.type(name, "Omer Studio");
    await user.click(await screen.findByRole("radio", { name: "#2563EB" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      const patch = studio.calls.find((call) => call.path === "/api/studio/preferences" && call.method === "PATCH");
      expect(patch?.body).toMatchObject({ brand_name: "Omer Studio", brand_color: "#2563EB" });
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
    expect(localStorage.getItem(BRAND_NAME_KEY)).toBe("Omer Studio");
  });

  it("saves the default shape and look, and can return to each template's own", async () => {
    const user = userEvent.setup();
    servePreferences();
    render(<SettingsPage section="defaults" />);

    expect(await screen.findByRole("radio", { name: "Keep each template's own shape" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Keep each template's own look" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: /Vertical/ }));
    await user.click(await screen.findByRole("radio", { name: /Bold pop/ }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      const patch = studio.calls.find((call) => call.path === "/api/studio/preferences" && call.method === "PATCH");
      expect(patch?.body).toMatchObject({ default_format: "9:16", default_theme: "pop" });
    });
    expect(localStorage.getItem(DEFAULT_FORMAT_KEY)).toBe("9:16");

    cleanup();
    render(<SettingsPage section="defaults" />);
    expect(await screen.findByRole("radio", { name: /Vertical/ })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: "Keep each template's own shape" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      const patches = studio.calls.filter((call) => call.path === "/api/studio/preferences" && call.method === "PATCH");
      expect(patches.at(-1)?.body).toMatchObject({ default_format: null });
    });
  });
});

describe("AI assistants", () => {
  it("connects an app, shows the restart hint, and offers Disconnect", async () => {
    const user = userEvent.setup();
    let connected = false;
    const done = app({ connected: true, restart_hint: "Restart Claude Desktop to finish." });
    studio.reply = (call) => {
      if (call.path === "/api/studio/setup/status") {
        return { status: 200, body: setupStatus({ ai_apps: [connected ? done : app()] }) };
      }
      if (call.path === "/api/studio/setup/ai-apps/claude-desktop/connect" && call.method === "POST") {
        connected = true;
        return { status: 200, body: done };
      }
      return null;
    };
    render(<SettingsPage section="ai" />);
    expect(screen.getByText(/Connecting adds Manim Studio to that app's settings\. Nothing else in them changes, and a backup is kept\./)).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Restart Claude Desktop to finish.")).toBeInTheDocument();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(studio.calls.some((call) => call.path === "/api/studio/setup/ai-apps/claude-desktop/connect" && call.method === "POST")).toBe(true);
  });

  it("disconnects an app", async () => {
    const user = userEvent.setup();
    let connected = true;
    studio.reply = (call) => {
      if (call.path === "/api/studio/setup/status") {
        return { status: 200, body: setupStatus({ ai_apps: [app({ connected })] }) };
      }
      if (call.path === "/api/studio/setup/ai-apps/claude-desktop/connect" && call.method === "DELETE") {
        connected = false;
        return { status: 200, body: app() };
      }
      return null;
    };
    render(<SettingsPage section="ai" />);

    await user.click(await screen.findByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("button", { name: "Connect" })).toBeInTheDocument();
    expect(studio.calls.some((call) => call.path === "/api/studio/setup/ai-apps/claude-desktop/connect" && call.method === "DELETE")).toBe(true);
  });

  it("fixes a saved connection that points to an older copy of the app", async () => {
    const user = userEvent.setup();
    let repaired = false;
    studio.reply = (call) => {
      if (call.path === "/api/studio/setup/status") {
        return { status: 200, body: setupStatus({ ai_apps: [repaired ? app({ connected: true }) : app({ connected: true, needs_repair: true })] }) };
      }
      if (call.path === "/api/studio/setup/ai-apps/claude-desktop/connect" && call.method === "POST") {
        repaired = true;
        return { status: 200, body: app({ connected: true, restart_hint: "Restart Claude Desktop to finish." }) };
      }
      return null;
    };
    render(<SettingsPage section="ai" />);

    expect(await screen.findByText("Connected, but it points to an older copy of Manim Studio.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Fix connection" }));
    expect(await screen.findByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fix connection" })).not.toBeInTheDocument();
    expect(studio.calls.some((call) => call.path === "/api/studio/setup/ai-apps/claude-desktop/connect" && call.method === "POST")).toBe(true);
  });

  it("shows the plain settings-file message and a retry when the file cannot be read", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    studio.reply = (call) => {
      if (call.path === "/api/studio/setup/status") return { status: 200, body: setupStatus() };
      if (call.path === "/api/studio/setup/ai-apps/claude-desktop/connect" && call.method === "POST") {
        attempts += 1;
        return { status: 409, body: { detail: "The claude_desktop_config.json file is damaged, so it was left unchanged. Fix or remove it, then try again." } };
      }
      return null;
    };
    render(<SettingsPage section="ai" />);

    await user.click(await screen.findByRole("button", { name: "Connect" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The claude_desktop_config.json file is damaged, so it was left unchanged.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(attempts).toBe(2));
  });

  it("shows the empty state, rechecks, and opens the manual setup", async () => {
    const user = userEvent.setup();
    let checks = 0;
    const none = [
      app({ id: "claude-desktop", label: "Claude Desktop", detected: false }),
      app({ id: "cursor", label: "Cursor", detected: false }),
    ];
    studio.reply = (call) => {
      if (call.path === "/api/studio/setup/status") {
        checks += 1;
        return { status: 200, body: setupStatus({ ai_apps: none }) };
      }
      if (call.path === "/api/studio/connection") {
        return { status: 200, body: { available: true, url: "http://127.0.0.1:8000/mcp/", token: "secret-token", stdio: { command: "manim-studio.exe", args: [], background: true } } };
      }
      return null;
    };
    render(<SettingsPage section="ai" />);

    expect(await screen.findByText("No AI apps found")).toBeInTheDocument();
    expect(screen.getByText("Install Claude, Cursor or another AI app, then come back.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Not on this computer" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect" })).not.toBeInTheDocument();

    const before = checks;
    await user.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(checks).toBeGreaterThan(before));

    await user.click(screen.getByRole("button", { name: "Set it up by hand" }));
    expect(await screen.findByRole("button", { name: "Copy setup prompt" })).toBeInTheDocument();
  });
});

describe("this computer", () => {
  it("sums up what is ready and installs an optional tool with progress", async () => {
    const user = userEvent.setup();
    let installed = false;
    const ffmpeg = component({
      id: "ffmpeg",
      label: "Sound tools",
      purpose: "Only needed by code scenes that add sound; templates do not use it.",
      status: "optional",
      required: false,
      can_install: true,
      detail: "Not installed. It can be added here without an administrator.",
    });
    const installing: SetupComponent = { ...ffmpeg, status: "installing", can_install: false, detail: "Starting the download...", progress: 40 };
    studio.reply = (call) => {
      if (call.path === "/api/studio/setup/status") {
        return { status: 200, body: setupStatus({ components: [component(), installed ? installing : ffmpeg] }) };
      }
      if (call.path === "/api/studio/setup/components/ffmpeg/install" && call.method === "POST") {
        installed = true;
        return { status: 202, body: { ...installing, progress: 0 } };
      }
      return null;
    };
    render(<SettingsPage section="system" />);

    expect(await screen.findByText("Everything you need is ready.")).toBeInTheDocument();
    expect(screen.getByText("Only needed by code scenes that add sound; templates do not use it.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Install" }));

    const bar = await screen.findByRole("progressbar", { name: "Installing Sound tools" });
    expect(bar).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByText("Installing… 40%")).toBeInTheDocument();
    expect(studio.calls.some((call) => call.path === "/api/studio/setup/components/ffmpeg/install" && call.method === "POST")).toBe(true);
  });

  it("recovers when the setup check fails", async () => {
    const user = userEvent.setup();
    let failing = true;
    studio.reply = (call) => {
      if (call.path !== "/api/studio/setup/status") return null;
      return failing ? { status: 500, body: { detail: "boom" } } : { status: 200, body: setupStatus() };
    };
    render(<SettingsPage section="system" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The app couldn't check this computer. Try again.");
    failing = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Everything you need is ready.")).toBeInTheDocument();
  });

  it("shows the data folder and opens it", async () => {
    const user = userEvent.setup();
    studio.reply = (call) => {
      if (call.path === "/api/studio/setup/status") return { status: 200, body: setupStatus() };
      if (call.path === "/api/studio/setup/reveal-data-folder") return { status: 204, body: null };
      return null;
    };
    render(<SettingsPage section="system" />);

    expect(await screen.findByText(String.raw`C:\Users\Omer\AppData\Roaming\Manim Studio`)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show folder" }));
    await waitFor(() => {
      expect(studio.calls.some((call) => call.path === "/api/studio/setup/reveal-data-folder" && call.method === "POST")).toBe(true);
    });
  });
});

describe("about", () => {
  it("shows the version when the app answers, and links to Author mode and the tour", async () => {
    studio.reply = (call) => call.path === "/api/health" ? { status: 200, body: { status: "online", version: "1.1.0" } } : null;
    render(<SettingsPage section="about" />);

    expect(await screen.findByText("1.1.0")).toBeInTheDocument();
    expect(screen.getByText("For people who write Manim code")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Author mode/ })).toHaveAttribute("href", "#/author");
    expect(screen.getByRole("link", { name: /welcome tour/ })).toHaveAttribute("href", "#/welcome");
  });
});
