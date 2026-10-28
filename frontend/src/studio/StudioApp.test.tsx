import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetCatalogCache } from "./api";
import { posterQueue } from "./hooks";
import { parseRoute, routeHash } from "./router";
import StudioApp from "./StudioApp";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

let studio: FakeStudio;

beforeEach(() => {
  resetCatalogCache();
  posterQueue.clear();
  window.history.replaceState(null, "", "/#/");
  studio = installFakeStudio();
});

function open(hash: string) {
  window.history.replaceState(null, "", `/${hash}`);
  return render(<StudioApp />);
}

describe("routes", () => {
  it("parses and builds hash routes", () => {
    expect(parseRoute("")).toEqual({ kind: "gallery" });
    expect(parseRoute("#/")).toEqual({ kind: "gallery" });
    expect(parseRoute("#/author")).toEqual({ kind: "author" });
    expect(parseRoute("#/new/countdown/break-timer")).toEqual({ kind: "new", template: "countdown", preset: "break-timer" });
    expect(parseRoute("#/project/abc%20d")).toEqual({ kind: "project", id: "abc d" });
    expect(parseRoute("#/nonsense")).toEqual({ kind: "gallery" });
    expect(routeHash({ kind: "project", id: "a/b" })).toBe("#/project/a%2Fb");
  });
});

describe("gallery", () => {
  it("fetches AI credentials only on opening, copies the HTTP configuration, and refetches on reopen", async () => {
    const user = userEvent.setup();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    studio.reply = (call) => call.path === "/api/studio/connection" ? {
      status: 200, body: { available: true, url: "http://127.0.0.1:8123/mcp/", token: "test-token" },
    } : null;
    open("#/");
    const connect = await screen.findByRole("button", { name: "Connect to AI" });
    expect(studio.calls.some((call) => call.path === "/api/studio/connection")).toBe(false);
    await user.click(connect);
    const configuration = await screen.findByRole("textbox", { name: "MCP configuration" });
    expect(JSON.parse((configuration as HTMLTextAreaElement).value)).toEqual({ mcpServers: { composer: {
      url: "http://127.0.0.1:8123/mcp/", headers: { Authorization: "Bearer test-token" },
    } } });
    await user.click(screen.getByRole("button", { name: "Copy configuration" }));
    expect(clipboard).toHaveBeenCalledWith((configuration as HTMLTextAreaElement).value);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(screen.getByText(/Keep this app open/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("textbox", { name: "MCP configuration" })).not.toBeInTheDocument();
    await user.click(connect);
    await screen.findByRole("textbox", { name: "MCP configuration" });
    expect(studio.calls.filter((call) => call.path === "/api/studio/connection")).toHaveLength(2);
  });

  it("handles unavailable AI connections and retries connection errors", async () => {
    const user = userEvent.setup();
    let failed = true;
    studio.reply = (call) => call.path === "/api/studio/connection"
      ? failed ? { status: 503, body: { detail: "Still starting." } } : { status: 200, body: { available: false } }
      : null;
    open("#/");
    await user.click(await screen.findByRole("button", { name: "Connect to AI" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Still starting.")).toBeInTheDocument();
    failed = false;
    await user.click(within(dialog).getByRole("button", { name: "Try again" }));
    expect(await within(dialog).findByText(/AI connections aren't available/)).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Copy configuration" })).not.toBeInTheDocument();
  });

  it("makes saved-video load failures visible and retryable", async () => {
    const user = userEvent.setup();
    let failed = true;
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 });
    studio.reply = (call) => call.path === "/api/studio/projects" && failed ? { status: 503, body: { detail: "Try later." } } : null;
    open("#/");
    expect(await screen.findByText(/Couldn't load your videos/)).toBeInTheDocument();
    failed = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: /My timer/ })).toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load your videos/)).not.toBeInTheDocument();
  });

  it("deletes a saved video after confirmation", async () => {
    const user = userEvent.setup();
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 });
    open("#/");
    await user.click(await screen.findByRole("button", { name: "Delete My timer" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: /My timer/ })).not.toBeInTheDocument());
    expect(studio.projects).toHaveLength(0);
  });
  it("shows a card per design with a poster, and filters them", async () => {
    const user = userEvent.setup();
    open("#/");
    expect(await screen.findByRole("heading", { name: "What are you making?" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Timers & countdowns" })).toBeInTheDocument();
    const card = screen.getByRole("link", { name: /Classroom timer/ });
    expect(card).toHaveAttribute("href", "#/new/countdown/classroom-timer");

    await waitFor(() => expect(studio.previews()).toHaveLength(3));
    const poster = studio.previews().find((request) => request.params.title === "Quiet reading time")!;
    expect(poster).toMatchObject({ template: "countdown", mode: "poster", settings: { aspect: "16:9", theme: "clean", energy: "calm" } });
    await waitFor(() => expect(card.querySelector("img")).toHaveAttribute("src", expect.stringMatching(/\/media\/studio\/previews\/\d\.png$/)));

    const search = screen.getByRole("searchbox", { name: "Search designs" });
    await user.type(search, "revenue");
    expect(screen.getByRole("link", { name: /Sales chart/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Classroom timer/ })).not.toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "classroom");
    // Template tags count too: both countdown cards match.
    expect(screen.getByRole("link", { name: /Classroom timer/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /10…1 countdown/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Sales chart/ })).not.toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "zebra");
    expect(screen.getByText(/Nothing matches "zebra"/)).toBeInTheDocument();
  });

  it("lists saved videos and links to author mode", async () => {
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: Date.now() / 1000 });
    open("#/");
    const saved = await screen.findByRole("link", { name: /My timer/ });
    expect(saved).toHaveAttribute("href", "#/project/p9");
    expect(screen.getByRole("link", { name: /Author mode/ })).toHaveAttribute("href", "#/author");
  });
});

describe("editor", () => {
  it("keeps invalid number edits visible instead of exporting the previous value", async () => {
    const user = userEvent.setup();
    open("#/new/chart/sales");
    const count = await screen.findByRole("textbox", { name: "How many" });
    fireEvent.change(count, { target: { value: "2.5" } });
    fireEvent.blur(count);
    expect(count).toHaveValue("2.5");
    expect(screen.getByText("Type a whole number.")).toBeInTheDocument();
    expect(count).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(count, { target: { value: "12" } });
    fireEvent.blur(count);
    expect(count).toHaveValue("12");
    expect(screen.getByText("From 1 to 9.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(studio.projects[0]?.params.count).toBe(12));
  });

  it("replaces a numeric cell's typed draft when spreadsheet rows are pasted", async () => {
    open("#/new/chart/sales");
    const cell = await screen.findByRole("textbox", { name: "Value, row 1" });
    fireEvent.change(cell, { target: { value: "99" } });
    fireEvent.paste(cell, { clipboardData: { getData: () => "25\ttrue\n30\tfalse" } });
    expect(cell).toHaveValue("25");
    expect(screen.getByRole("textbox", { name: "Value, row 2" })).toHaveValue("30");
    await waitFor(() => expect((studio.previews().at(-1)?.params.bars as Array<{ value: number }>)[0].value).toBe(25));
  });

  it("saves an untouched preset and retries a refused save without another edit", async () => {
    const user = userEvent.setup();
    let failed = true;
    studio.reply = (call) => call.method === "POST" && call.path === "/api/studio/projects" && failed
      ? { status: 503, body: { detail: "Save is temporarily unavailable." } } : null;
    open("#/new/countdown/classroom-timer");
    await user.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Save is temporarily unavailable/)).toBeInTheDocument();
    failed = false;
    await user.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(window.location.hash).toBe("#/project/p1"));
    expect(studio.projects).toHaveLength(1);
    expect(studio.projects[0].params.seconds).toBe(300);
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("reloads AI edits without saving over them, and prevents reload while locally dirty", async () => {
    const user = userEvent.setup();
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: { title: "Original", seconds: 300 }, settings: {}, created: 1, updated: 1 });
    open("#/project/p9");
    await screen.findByRole("textbox", { name: "Title" });
    studio.projects[0].params = { title: "Changed by AI", seconds: 60 };
    studio.projects[0].title = "AI timer";
    await user.click(screen.getByRole("button", { name: "Reload saved" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Changed by AI"));
    expect(screen.getByRole("textbox", { name: "Timer length" })).toHaveValue("1:00");
    expect(screen.getByRole("textbox", { name: "Video title" })).toHaveValue("AI timer");
    expect(studio.calls.some((call) => call.method === "PUT")).toBe(false);
    fireEvent.change(screen.getByRole("textbox", { name: "Title" }), { target: { value: "My own edits" } });
    expect(screen.getByRole("button", { name: "Reload saved" })).toBeDisabled();
  });

  it("keeps edits typed while a reload request is still running", async () => {
    const user = userEvent.setup();
    studio.projects.push({ id: "p9", title: "My timer", template: "countdown", params: {}, settings: {}, created: 1, updated: 1 });
    open("#/project/p9");
    const title = await screen.findByRole("textbox", { name: "Title" });
    let finish!: (result: { status: number; body: unknown }) => void;
    studio.reply = (call) => call.path === "/api/studio/projects/p9" && call.method === "GET"
      ? new Promise((resolve) => { finish = resolve; }) : null;
    await user.click(screen.getByRole("button", { name: "Reload saved" }));
    fireEvent.change(title, { target: { value: "Keep my edit" } });
    await act(async () => { finish({ status: 200, body: { ...studio.projects[0], params: { title: "Remote edit" } } }); });
    expect(title).toHaveValue("Keep my edit");
    expect(await screen.findByText(/Your edits were kept/)).toBeInTheDocument();
  });

  it("uses the server's cancellation result when an export has already finished", async () => {
    const user = userEvent.setup();
    studio.reply = (call) => call.path === "/api/studio/exports/e1" && call.method === "DELETE" ? {
      status: 200, body: { ...studio.exports[0], status: "done", url: "/media/studio/exports/e1.mp4", filename: "timer.mp4", progress: 100 },
    } : null;
    open("#/new/countdown/classroom-timer");
    await user.click(await screen.findByRole("button", { name: "Export" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Make video" }));
    await user.click(await within(dialog).findByRole("button", { name: "Cancel export" }));
    expect(await within(dialog).findByRole("heading", { name: "Your file is ready" })).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Download" })).toHaveAttribute("download", "timer.mp4");
  });
  it("builds the form from the schema and previews edits", async () => {
    const user = userEvent.setup();
    open("#/new/chart/sales");
    const headline = await screen.findByRole("textbox", { name: "Headline" });
    expect(headline).toHaveValue("Our *best* year");
    expect(screen.getByText("15/80")).toBeInTheDocument();
    expect(screen.getByText(/Tip: \*best\* becomes/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Label, row 2" })).toHaveValue("2024");
    expect(screen.getByRole("button", { name: /^Point 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change" })).toBeInTheDocument(); // the point's icon
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument(); // the logo
    expect(screen.getByRole("textbox", { name: "How many" })).toHaveValue("3");
    expect(screen.getByRole("radiogroup", { name: "Format" })).toBeInTheDocument();

    // The first preview goes out at once with the whole look.
    await waitFor(() => expect(studio.previews().length).toBeGreaterThan(0));
    expect(studio.previews()[0]).toMatchObject({
      template: "chart",
      mode: "poster",
      settings: { aspect: "16:9", theme: "clean", energy: "normal", ending: "hold", locale: "en", background: { kind: "theme" } },
    });

    await user.clear(headline);
    await user.type(headline, "Big news");
    await waitFor(() => expect(studio.previews().at(-1)?.params.headline).toBe("Big news"));
    // Typing is debounced: far fewer previews than keystrokes.
    expect(studio.previews().length).toBeLessThan(5);

    // The first edit creates the project and the URL follows, without reloading the editor.
    await waitFor(() => expect(studio.projects).toHaveLength(1));
    expect(studio.projects[0]).toMatchObject({ template: "chart", title: "Sales chart" });
    await waitFor(() => expect(window.location.hash).toBe("#/project/p1"));
    expect(screen.getByRole("textbox", { name: "Headline" })).toHaveValue("Big news");
    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());

    await user.click(screen.getByRole("radio", { name: /Tall/ }));
    await waitFor(() => expect(studio.previews().at(-1)?.settings.aspect).toBe("9:16"));
  });

  it("shows validation errors on the right fields", async () => {
    const user = userEvent.setup();
    studio.previewReply = (request) =>
      request.params.headline === "x"
        ? {
            status: 422,
            body: {
              detail: "Invalid input for chart.",
              errors: [
                { field: "params.headline", message: "String should have at least 3 characters" },
                { field: "params.bars.1.value", message: "Input should be less than or equal to 100" },
                { field: "settings.length", message: "Input should be less than or equal to 60" },
              ],
            },
          }
        : null;
    open("#/new/chart/sales");
    const headline = await screen.findByRole("textbox", { name: "Headline" });
    await user.clear(headline);
    await user.type(headline, "x");
    expect(await screen.findByText("Use at least 3 characters.")).toBeInTheDocument();
    expect(headline).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Row 2, Value: Use 100 or less.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Value, row 2" })).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/Some fields need a fix/)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Look/ }));
    expect(await screen.findByText("Use 60 or less.")).toBeInTheDocument();
  });

  it("pastes rows from a spreadsheet into a table", async () => {
    open("#/new/chart/sales");
    const cell = await screen.findByRole("textbox", { name: "Label, row 1" });
    fireEvent.paste(cell, { clipboardData: { getData: () => "Label\tValue\tHighlight\nNorth\t1.234,5\tyes\nSouth\t2\tno\nWest\t3\t\n" } });
    expect(await screen.findByText("Pasted 3 rows (the header row was left out).")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Label, row 3" })).toHaveValue("West");
    expect(screen.getByRole("textbox", { name: "Value, row 1" })).toHaveValue("1234.5");
    expect(screen.getByRole("checkbox", { name: "Highlight, row 1" })).toBeChecked();
    await waitFor(() =>
      expect(studio.previews().at(-1)?.params.bars).toEqual([
        { label: "North", value: 1234.5, highlight: true },
        { label: "South", value: 2, highlight: false },
        { label: "West", value: 3, highlight: false },
      ]),
    );
  });

  it("adds, moves and removes list items", async () => {
    const user = userEvent.setup();
    open("#/new/chart/sales");
    await screen.findByRole("button", { name: /^Point 1/ });
    await user.click(screen.getByRole("button", { name: "Add point" }));
    const second = screen.getAllByRole("textbox", { name: "Text" })[1];
    await user.type(second, "Cheap");
    await user.click(screen.getByRole("button", { name: "Move Point 2 up" }));
    expect(screen.getAllByRole("textbox", { name: "Text" }).map((input) => (input as HTMLInputElement).value)).toEqual(["Cheap", "Fast"]);
    // maxItems is 3.
    await user.click(screen.getByRole("button", { name: "Add point" }));
    expect(screen.getByRole("button", { name: "Add point" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Remove Point 3" }));
    expect(screen.getAllByRole("textbox", { name: "Text" })).toHaveLength(2);
    await waitFor(() => expect(studio.previews().at(-1)?.params.points).toEqual([{ text: "Cheap", icon: null }, { text: "Fast", icon: "clock" }]));
  });

  it("uses mm:ss for durations and hides the length slider when the content sets it", async () => {
    const user = userEvent.setup();
    open("#/new/countdown/classroom-timer");
    const timer = await screen.findByRole("textbox", { name: "Timer length" });
    expect(timer).toHaveValue("5:00");
    await user.click(screen.getByRole("button", { name: "30 seconds more" }));
    expect(timer).toHaveValue("5:30");
    await user.clear(timer);
    await user.type(timer, "2:15{Enter}");
    expect(timer).toHaveValue("2:15");
    await waitFor(() => expect(studio.previews().at(-1)?.params.seconds).toBe(135));
    expect(screen.getByRole("radiogroup", { name: "Style" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Look/ }));
    expect(await screen.findByRole("radiogroup", { name: "Theme" })).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
  });

  it("exports a file and offers the download", async () => {
    const user = userEvent.setup();
    open("#/new/countdown/launch-countdown");
    await screen.findByRole("textbox", { name: "Timer length" });
    await user.click(screen.getByRole("button", { name: "Export" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: /GIF/ }));
    await user.click(within(dialog).getByRole("radio", { name: /720p/ }));
    await user.click(within(dialog).getByRole("button", { name: "Make GIF" }));
    await waitFor(() => expect(studio.exports).toHaveLength(1));
    expect(studio.exports[0]).toMatchObject({ template: "countdown", format: "gif", quality: "720p", title: "10…1 countdown" });
    expect(await within(dialog).findByText(/Waiting to start/)).toBeInTheDocument();

    act(() => {
      Object.assign(studio.exports[0], { status: "done", progress: 100, url: "/media/studio/exports/e1.gif", filename: "countdown.gif", size: 2048 });
    });
    const download = await within(dialog).findByRole("link", { name: "Download" }, { timeout: 4000 });
    expect(download).toHaveAttribute("href", "/media/studio/exports/e1.gif");
    expect(download).toHaveAttribute("download", "countdown.gif");
    expect(within(dialog).getByRole("img", { name: "Your export" })).toBeInTheDocument();
  });

  it("explains a missing project", async () => {
    open("#/project/gone");
    expect(await screen.findByText("This video couldn't be found.")).toBeInTheDocument();
  });
});
