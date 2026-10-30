import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { resetCatalogCache } from "./api";
import { posterQueue } from "./hooks";
import { OnboardingPage } from "./Onboarding";
import {
  BRAND_COLOR_KEY,
  BRAND_NAME_KEY,
  DEFAULT_FORMAT_KEY,
  ONBOARDING_KEY,
  resetPreferencesForTests,
} from "./preferences";
import type { AIApp, SetupComponent, SetupStatus } from "./setup";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

let studio: FakeStudio;

const renderer: SetupComponent = {
  id: "renderer",
  label: "Video renderer",
  purpose: "Draws every video.",
  status: "ready",
  required: true,
  can_install: false,
  detail: "Manim is ready.",
  progress: null,
};

const sound: SetupComponent = {
  id: "ffmpeg",
  label: "Sound tools",
  purpose: "Only needed by some code scenes.",
  status: "optional",
  required: false,
  can_install: true,
  detail: "Not installed.",
  progress: null,
};

const claude: AIApp = {
  id: "claude-desktop",
  label: "Claude Desktop",
  detected: true,
  connected: false,
  needs_repair: false,
  restart_hint: null,
  error: null,
};

function setupStatus(overrides: Partial<SetupStatus> = {}): SetupStatus {
  return {
    platform: "windows",
    mode: "desktop",
    components: [renderer, sound],
    ai_apps: [claude],
    data_folder: String.raw`C:\Users\Omer\Videos`,
    ...overrides,
  };
}

function reply(call: { path: string; method: string; body: unknown }) {
  if (call.path === "/api/studio/setup/status") return { status: 200, body: setupStatus() };
  if (call.path === "/api/studio/preferences" && call.method === "PATCH") {
    return { status: 200, body: { ...(call.body as object) } };
  }
  return null;
}

beforeEach(() => {
  resetPreferencesForTests();
  resetCatalogCache();
  posterQueue.clear();
  window.history.replaceState(null, "", "/#/welcome");
  studio = installFakeStudio();
  studio.reply = reply;
});

function nameField() {
  return screen.getByRole("textbox", { name: "Your name or business" });
}

describe("the welcome tour", () => {
  it("asks five real questions and announces where you are", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    expect(screen.getByRole("heading", { name: /What should we call you\?/ })).toHaveFocus();
    expect(screen.getByText("Step 1 of 5")).toBeInTheDocument();
    await waitFor(() => expect(studio.previews().length).toBeGreaterThan(0));
    expect(studio.previews()[0]).toMatchObject({ mode: "poster" });

    await user.type(nameField(), "Ada");
    expect(screen.getByText("Welcome, Ada")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(screen.getByRole("heading", { name: /What will you make most\?/ })).toHaveFocus();
    expect(screen.getByText("Step 2 of 5")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Vertical/ }));
    await waitFor(() => expect(studio.previews().at(-1)?.settings.aspect).toBe("9:16"));
    expect(screen.getByText("Vertical · 9:16")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: /Pick your colour\./ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: /Bring your AI along\?/ })).toBeInTheDocument();
    expect(screen.getByText("Optional. Your AI assistant can then make videos here for you.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: /You're ready\./ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start making videos" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Skip" })).not.toBeInTheDocument();
  });

  it("skips ahead to the ready step without saving anything", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.type(nameField(), "Ada");
    await user.click(screen.getByRole("button", { name: "Skip" }));

    expect(screen.getByRole("heading", { name: /You're ready\./ })).toBeInTheDocument();
    expect(screen.getByText("Step 5 of 5")).toBeInTheDocument();
    expect(localStorage.getItem(BRAND_NAME_KEY)).toBeNull();
    expect(studio.calls.some((call) => call.path === "/api/studio/preferences" && call.method === "PATCH")).toBe(false);
  });

  it("prefills saved answers when the tour is opened again", async () => {
    localStorage.setItem(BRAND_NAME_KEY, "Ada Studio");
    localStorage.setItem(BRAND_COLOR_KEY, "#FF3366");
    localStorage.setItem(DEFAULT_FORMAT_KEY, "9:16");
    const user = userEvent.setup();
    render(<OnboardingPage />);

    expect(nameField()).toHaveValue("Ada Studio");
    await waitFor(() => expect(studio.previews()[0]?.settings).toMatchObject({
      aspect: "9:16",
      brand: { accent: "#FF3366" },
    }));

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("radio", { name: /Vertical/ })).toHaveAttribute("aria-checked", "true");

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("button", { name: "Custom color #FF3366" })).toBeInTheDocument();
  });

  it("sets onboarding_done and goes home from the last step", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.click(screen.getByRole("button", { name: "Skip" }));
    await user.click(screen.getByRole("button", { name: "Start making videos" }));

    expect(localStorage.getItem(ONBOARDING_KEY)).toBe("true");
    expect(window.location.hash).toBe("#/");
    await waitFor(() => {
      const saved = studio.calls.find((call) => call.path === "/api/studio/preferences" && call.method === "PATCH");
      expect(saved?.body).toMatchObject({ onboarding_done: true });
    });
  });

  it("goes back to the previous question with its answer kept", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.type(nameField(), "Ada");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("radio", { name: /Square/ }));
    await user.click(screen.getByRole("button", { name: "Back" }));

    expect(nameField()).toHaveValue("Ada");
    expect(screen.getByRole("heading", { name: /What should we call you\?/ })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("radio", { name: /Square/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("heading", { name: /What will you make most\?/ })).toHaveFocus();
  });

  it("submits the current step with Enter", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.type(nameField(), "Ada");
    fireEvent.keyDown(nameField(), { key: "Enter" });

    expect(screen.getByRole("heading", { name: /What will you make most\?/ })).toBeInTheDocument();
    expect(localStorage.getItem(BRAND_NAME_KEY)).toBe("Ada");
  });

  it("saves each answer as the tour continues", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.type(nameField(), "Ada");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("radio", { name: /Square/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(within(screen.getByRole("radiogroup", { name: "Quick colours" })).getByRole("radio", { name: "#10B981" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(localStorage.getItem(BRAND_NAME_KEY)).toBe("Ada");
    expect(localStorage.getItem(DEFAULT_FORMAT_KEY)).toBe("1:1");
    expect(localStorage.getItem(BRAND_COLOR_KEY)).toBe("#10B981");
    await waitFor(() => {
      const patches = studio.calls.filter((call) => call.path === "/api/studio/preferences" && call.method === "PATCH");
      const sent = Object.assign({}, ...patches.map((call) => call.body as object));
      expect(sent).toMatchObject({ brand_name: "Ada", default_format: "1:1", brand_color: "#10B981" });
      expect(sent).not.toHaveProperty("onboarding_done");
    });
  });

  it("never connects an AI app by itself", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("button", { name: "Connect" })).toBeInTheDocument();
    expect(screen.getByText("Claude Desktop")).toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(studio.calls.some((call) => /\/api\/studio\/setup\/ai-apps\/.+\/connect$/.test(call.path))).toBe(false);
    expect(screen.getByText("I made your sale video")).toBeInTheDocument();
    expect(screen.getByText("Just an example. Nothing is connected until you choose Connect.")).toBeInTheDocument();
  });

  it("keeps going when the preview cannot be drawn", async () => {
    const user = userEvent.setup();
    studio.previewReply = () => ({ status: 500, body: { detail: "boom" } });
    render(<OnboardingPage />);

    expect(await screen.findByText("The preview can't be drawn right now. You can keep going.")).toBeInTheDocument();
    await user.type(nameField(), "Ada");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: /What will you make most\?/ })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Landscape/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("button", { name: "Start making videos" })).toBeInTheDocument();
  });

  it("keeps the questions working when the catalog fails", async () => {
    studio.reply = (call) => call.path === "/api/studio/catalog" ? { status: 500, body: { detail: "boom" } } : reply(call);
    const user = userEvent.setup();
    render(<OnboardingPage />);

    expect(await screen.findByText("Previews aren't available right now. You can still make your choices.")).toBeInTheDocument();
    await user.type(nameField(), "Ada");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("heading", { name: /What will you make most\?/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Landscape/ })).toBeInTheDocument();
  });

  it("debounces the colour so a burst of choices asks for one poster", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await waitFor(() => expect(studio.previews().length).toBe(1));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const swatches = screen.getByRole("radiogroup", { name: "Quick colours" });
    fireEvent.click(within(swatches).getByRole("radio", { name: "#E11D48" }));
    fireEvent.click(within(swatches).getByRole("radio", { name: "#F97316" }));
    fireEvent.click(within(swatches).getByRole("radio", { name: "#8B5CF6" }));

    await waitFor(() => expect(studio.previews().at(-1)?.settings.brand).toEqual({ accent: "#8B5CF6" }), { timeout: 2000 });
    const accents = studio.previews()
      .map((request) => (request.settings.brand as { accent?: string } | undefined)?.accent)
      .filter(Boolean);
    expect(accents).not.toContain("#E11D48");
    expect(accents).not.toContain("#F97316");
    expect(accents).toEqual(["#8B5CF6"]);
  });

  it("keeps the old picture and shows a quiet spinner while the next one is drawn", async () => {
    let release: (() => void) | undefined;
    studio.reply = (call) => {
      if (call.path === "/api/studio/preview" && (call.body as { settings?: { brand?: unknown } }).settings?.brand) {
        return new Promise((resolve) => {
          release = () => resolve({
            status: 200,
            body: { url: "/media/studio/previews/new.png", mode: "poster", width: 640, height: 360 },
          });
        });
      }
      return reply(call);
    };
    const user = userEvent.setup();
    render(<OnboardingPage />);

    const first = await screen.findByRole("img", { name: /preview$/ });
    const firstSrc = first.getAttribute("src");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Quick colours" })).getByRole("radio", { name: "#2563EB" }));
    await waitFor(() => expect(studio.previews().length).toBe(2), { timeout: 2000 });

    expect(screen.getByRole("img", { name: /preview$/ })).toHaveAttribute("src", firstSrc);
    expect(screen.getByText("Updating the preview…")).toBeInTheDocument();

    release?.();
    await waitFor(() => expect(screen.getByRole("img", { name: /preview$/ })).toHaveAttribute("src", "/media/studio/previews/new.png"));
    expect(screen.queryByText("Updating the preview…")).not.toBeInTheDocument();
  });

  it("shows only what is needed on the last step and offers no Install buttons", async () => {
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.click(screen.getByRole("button", { name: "Skip" }));

    expect(await screen.findByText("Everything you need is ready.")).toBeInTheDocument();
    expect(screen.getByText("Video renderer")).toBeInTheDocument();
    expect(screen.queryByText("Sound tools")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Install" })).not.toBeInTheDocument();
  });

  it("shows the plain problem and Try again when something needed is missing, without blocking", async () => {
    studio.reply = (call) => call.path === "/api/studio/setup/status"
      ? { status: 200, body: setupStatus({ components: [{ ...renderer, status: "missing", detail: "The video renderer is missing." }] }) }
      : reply(call);
    const user = userEvent.setup();
    render(<OnboardingPage />);

    await user.click(screen.getByRole("button", { name: "Skip" }));

    expect(await screen.findByText("Something you need isn't ready yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start making videos" })).toBeEnabled();
  });
});
