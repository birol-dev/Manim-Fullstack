import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { UpdateSection } from "./UpdateSection";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";
import type { UpdateStatus } from "./setup";

let studio: FakeStudio;

function status(overrides: Partial<UpdateStatus> = {}): UpdateStatus {
  return { state: "idle", version: null, notes: "", progress: null, detail: null, message: null, ...overrides };
}

function serve(update: UpdateStatus, extra?: (call: { path: string; method: string }) => { status: number; body: unknown } | null) {
  studio.reply = (call) => {
    if (call.path === "/api/studio/setup/status") return { status: 200, body: { version: "1.3.0" } };
    if (call.path === "/api/studio/setup/update") return { status: 200, body: update };
    if (call.path === "/api/studio/preferences") return { status: 200, body: { update_check: true } };
    return extra?.(call) ?? null;
  };
}

beforeEach(() => {
  studio = installFakeStudio();
});

it("shows the version, the plain state, and a check button", async () => {
  serve(status({ detail: "You're using the latest version." }));
  render(<UpdateSection />);

  expect(await screen.findByText("1.3.0")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Check for updates" })).toBeInTheDocument();
  expect(screen.getByText("You're using the latest version.")).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "Check for updates automatically" })).toBeChecked();
});

it("offers a newer version with its notes and downloads only after the click", async () => {
  const user = userEvent.setup();
  serve(
    status({ state: "available", version: "1.4.0", notes: "Faster exports." }),
    (call) => call.path === "/api/studio/setup/update/download"
      ? { status: 200, body: status({ state: "downloading", version: "1.4.0", progress: 42 }) }
      : null,
  );
  render(<UpdateSection />);

  expect(await screen.findByText("Version 1.4.0 is available")).toBeInTheDocument();
  expect(screen.getByText("Faster exports.")).toBeInTheDocument();
  expect(studio.calls.some((call) => call.method === "POST" && call.path === "/api/studio/setup/update/download")).toBe(false);

  await user.click(screen.getByRole("button", { name: "Download update" }));
  expect(await screen.findByRole("progressbar", { name: "Update download progress" })).toHaveAttribute("aria-valuenow", "42");
  expect(screen.getByText("42%")).toBeInTheDocument();
  expect(studio.calls.some((call) => call.method === "POST" && call.path === "/api/studio/setup/update/download")).toBe(true);
});

it("restarts and installs only when the person asks", async () => {
  const user = userEvent.setup();
  serve(
    status({ state: "ready", version: "1.4.0" }),
    (call) => call.path === "/api/studio/setup/update/install"
      ? { status: 200, body: status({ state: "ready", version: "1.4.0", detail: "Manim Studio is closing to install the update." }) }
      : null,
  );
  render(<UpdateSection />);

  expect(await screen.findByText("Version 1.4.0 is ready to install.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Restart and update" }));
  expect(await screen.findByText("Manim Studio is closing to install the update.")).toBeInTheDocument();
  expect(studio.calls.filter((call) => call.method === "POST" && call.path === "/api/studio/setup/update/install")).toHaveLength(1);
});

it("shows a failed update in plain words once the server reports it", async () => {
  serve(status({ state: "failed", detail: "The update file was damaged, so it was not used. Try again.",
    message: "The update file was damaged, so it was not used. Try again." }));
  render(<UpdateSection />);

  expect(await screen.findByRole("alert")).toHaveTextContent("The update file was damaged, so it was not used. Try again.");
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

it("saves the automatic-check choice", async () => {
  const user = userEvent.setup();
  studio.reply = (call) => {
    if (call.path === "/api/studio/setup/status") return { status: 200, body: { version: "1.3.0" } };
    if (call.path === "/api/studio/setup/update") return { status: 200, body: status() };
    if (call.path === "/api/studio/preferences" && call.method === "GET") return { status: 200, body: { update_check: false } };
    if (call.path === "/api/studio/preferences" && call.method === "PATCH") return { status: 200, body: call.body };
    return null;
  };
  render(<UpdateSection />);

  const toggle = await screen.findByRole("checkbox", { name: "Check for updates automatically" });
  await waitFor(() => expect(toggle).not.toBeChecked());
  await user.click(toggle);
  expect(toggle).toBeChecked();
  await waitFor(() => {
    const patch = studio.calls.find((call) => call.path === "/api/studio/preferences" && call.method === "PATCH");
    expect(patch?.body).toEqual({ update_check: true });
  });
});

it("says plainly when the app runs from source", async () => {
  serve(status({ state: "unavailable", detail: "You're running from source. Use git pull to update." }));
  render(<UpdateSection />);

  expect(await screen.findByText("You're running from source. Use git pull to update.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Check for updates|Download update|Restart and update|Try again/ })).not.toBeInTheDocument();
});
