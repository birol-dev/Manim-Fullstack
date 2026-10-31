import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { EditorPage } from "./Editor";
import { MakeManyPage } from "./MakeMany";
import type { ParseBatchRequest, StartBatchRequest } from "./api";
import { installFakeStudio } from "./test/fakeStudio";
import { CATALOG } from "./test/fixtures";
import type { BatchRowProblem, ParsedBatch } from "./types";

beforeEach(() => {
  window.location.hash = "";
});

const PARSED: ParsedBatch = {
  headers: ["Title", "Timer length"],
  rows: [["Quick timer", "3"], ["Long timer", "5"]],
  fields: [
    { field: "title", label: "Title", kind: "text", max_length: 60, required: false },
    { field: "seconds", label: "Timer length", kind: "number" },
  ],
  suggested_mapping: { title: 0, seconds: 1 },
  suggested_title_column: 0,
};

const PROBLEM: BatchRowProblem = {
  row: 2,
  title: "Long timer",
  errors: [{ field: "params.seconds", label: "Timer length", message: "Use 3 or more." }],
};

function batchReply(problem: BatchRowProblem | null = null) {
  const studio = installFakeStudio();
  studio.reply = (call) => {
    if (call.path === "/api/studio/batches/parse") {
      const body = call.body as ParseBatchRequest;
      return body.rows
        ? { status: 200, body: { ...PARSED, row_errors: problem ? [problem] : [], valid_rows: problem ? 1 : 2 } }
        : { status: 200, body: PARSED };
    }
    if (call.path === "/api/studio/batches" && call.method === "POST") {
      return {
        status: 202,
        body: {
          batch_id: "b1", export_ids: ["e1"], row_errors: problem ? [problem] : [],
          batch: { id: "b1", name: "Countdown timer — 1 video", template: "countdown", title: "Countdown timer",
            total: 1, counts: { queued: 1, rendering: 0, done: 0, failed: 0, cancelled: 0 } },
        },
      };
    }
    return null;
  };
  return studio;
}

it("walks a pasted list through matching, a row preview and making the videos", async () => {
  const user = userEvent.setup();
  const studio = batchReply(PROBLEM);
  render(<MakeManyPage catalog={CATALOG} route={{ kind: "many", template: "countdown", preset: "classroom-timer" }} />);

  expect(await screen.findByRole("heading", { name: /Where's your list/ })).toBeInTheDocument();
  const paste = screen.getByLabelText("Paste rows from a spreadsheet");
  await user.type(paste, "Title,Timer length\nQuick timer,3\nLong timer,5");
  await user.click(screen.getByRole("button", { name: "Use this list" }));

  expect(await screen.findByRole("heading", { name: /Match your columns/ })).toBeInTheDocument();
  expect(screen.getByLabelText("Title")).toHaveValue("0");
  expect(screen.getByLabelText("Timer length")).toHaveValue("1");
  expect(screen.getByLabelText("Name each video from")).toHaveValue("0");
  expect(await screen.findByText("Row 1 of 2 · Quick timer")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Next row" }));
  expect(screen.getByText("Row 2 of 2 · Long timer")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Previous row" }));
  expect(screen.getByText("Row 1 of 2 · Quick timer")).toBeInTheDocument();
  expect(studio.previews().some((request) => request.params.title === "Quick timer")).toBe(true);

  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByRole("heading", { name: /Ready to make 1 video/ })).toBeInTheDocument();
  expect(screen.getByText("Skip this row. It needs a fix first:")).toBeInTheDocument();
  expect(screen.getByText("Timer length: Use 3 or more.")).toBeInTheDocument();

  const make = screen.getByRole("button", { name: "Make 1 video" });
  await waitFor(() => expect(make).toBeEnabled());
  await user.selectOptions(screen.getByLabelText("Quality"), "draft");
  await user.click(make);
  await waitFor(() => expect(studio.calls.some((call) => call.path === "/api/studio/batches" && call.method === "POST")).toBe(true));
  const body = studio.calls.find((call) => call.path === "/api/studio/batches" && call.method === "POST")?.body as StartBatchRequest;
  expect(body).toEqual(expect.objectContaining({
    template: "countdown",
    mapping: { title: 0, seconds: 1 },
    title_column: 0,
    format: "mp4",
    quality: "draft",
    rows: PARSED.rows,
  }));
  await waitFor(() => expect(window.location.hash).toBe("#/exports"));
});

it("explains a row the preview cannot draw in plain words", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  const parsed: ParsedBatch = {
    ...PARSED,
    rows: [["Impossible timer", "3"], ["Unusable timer", "5"]],
  };
  studio.reply = (call) => {
    if (call.path === "/api/studio/batches/parse") {
      return { status: 200, body: { ...parsed, row_errors: [], valid_rows: 2 } };
    }
    return null;
  };
  studio.previewReply = (request) => (request.params.title === "Unusable timer"
    ? { status: 422, body: { detail: "Invalid input for countdown.", errors: [{ field: "params.seconds", message: "String should have at most 60 characters" }] } }
    : null);
  render(<MakeManyPage catalog={CATALOG} route={{ kind: "many", template: "countdown", preset: "classroom-timer" }} />);
  await screen.findByRole("heading", { name: /Where's your list/ });
  await user.type(screen.getByLabelText("Paste rows from a spreadsheet"), "Title,Timer length\nImpossible timer,3\nUnusable timer,5");
  await user.click(screen.getByRole("button", { name: "Use this list" }));
  await screen.findByRole("heading", { name: /Match your columns/ });

  await user.click(screen.getByRole("button", { name: "Next row" }));
  expect(await screen.findByText("This row needs a fix first: Use at most 60 characters.")).toBeInTheDocument();
  expect(studio.previews().some((request) => request.params.title === "Unusable timer")).toBe(true);
});

it("keeps the pasted list when going back a step", async () => {
  const user = userEvent.setup();
  batchReply();
  render(<MakeManyPage catalog={CATALOG} route={{ kind: "many", template: "countdown", preset: "classroom-timer" }} />);
  await screen.findByRole("heading", { name: /Where's your list/ });
  const text = "Title,Timer length\nQuick timer,3\nLong timer,5";
  await user.type(screen.getByLabelText("Paste rows from a spreadsheet"), text);
  await user.click(screen.getByRole("button", { name: "Use this list" }));
  await screen.findByRole("heading", { name: /Match your columns/ });

  await user.click(screen.getByRole("button", { name: "Back" }));
  expect(screen.getByRole("heading", { name: /Where's your list/ })).toBeInTheDocument();
  expect(screen.getByLabelText("Paste rows from a spreadsheet")).toHaveValue(text);
  expect(screen.getByRole("button", { name: "Use this list" })).toBeEnabled();
});

it("reads a chosen CSV file as bytes and reports a plain error for the wrong file", async () => {
  const user = userEvent.setup();
  const studio = batchReply();
  render(<MakeManyPage catalog={CATALOG} route={{ kind: "many", template: "countdown", preset: "classroom-timer" }} />);
  await screen.findByRole("heading", { name: /Where's your list/ });

  await user.upload(screen.getByLabelText("Choose a file"), new File(["Title,Timer length\nQuick,3"], "class list.csv", { type: "text/csv" }));
  await waitFor(() => expect(studio.calls.some((call) => call.path === "/api/studio/batches/parse")).toBe(true));
  const body = studio.calls.find((call) => call.path === "/api/studio/batches/parse")?.body as ParseBatchRequest;
  expect(body.filename).toBe("class list.csv");
  expect(body.data).toBeTruthy();
  expect(await screen.findByRole("heading", { name: /Match your columns/ })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Back" }));
  fireEvent.change(screen.getByLabelText("Choose a file"), {
    target: { files: [new File(["x"], "notes.pdf", { type: "application/pdf" })] },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose a CSV, TSV or .xlsx file.");
});

it("opens a saved project's own words and look", async () => {
  const studio = installFakeStudio();
  studio.projects = [{
    id: "p1", title: "Maths timer", template: "countdown",
    params: { seconds: 9, title: "Maths", style: "ring" }, settings: { theme: "pop" }, created: 1, updated: 1,
  }];
  render(<MakeManyPage catalog={CATALOG} route={{ kind: "many-project", id: "p1" }} />);
  expect(await screen.findByRole("heading", { name: /Where's your list/ })).toBeInTheDocument();
  await waitFor(() => expect(studio.previews().length).toBeGreaterThan(0));
  expect(studio.previews()[0].params).toEqual(expect.objectContaining({ seconds: 9, title: "Maths" }));
  expect(studio.previews()[0].settings).toEqual(expect.objectContaining({ theme: "pop" }));
});

it("opens the list maker from the editor's Make many button", async () => {
  const user = userEvent.setup();
  const studio = installFakeStudio();
  studio.projects = [{
    id: "p1", title: "Maths timer", template: "countdown",
    params: { seconds: 9, title: "Maths", style: "ring" }, settings: { theme: "pop" }, created: 1, updated: 1,
  }];
  render(<TooltipProvider><EditorPage catalog={CATALOG} route={{ kind: "project", id: "p1" }} onProjectCreated={vi.fn()} /></TooltipProvider>);
  expect(await screen.findByDisplayValue("Maths timer")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Make many" }));
  expect(window.location.hash).toBe("#/many/project/p1");
});

it("downloads a sample file with this design's fields and two rows", async () => {
  const user = userEvent.setup();
  installFakeStudio();
  const captured: HTMLAnchorElement[] = [];
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    captured.push(this);
  });
  try {
    render(<MakeManyPage catalog={CATALOG} route={{ kind: "many", template: "countdown", preset: "classroom-timer" }} />);
    await screen.findByRole("heading", { name: /Where's your list/ });
    await user.click(screen.getByRole("button", { name: "Get a sample file" }));
    expect(click).toHaveBeenCalledTimes(1);
    const href = captured[0]?.href ?? "";
    if (href.startsWith("data:")) {
      const csv = decodeURIComponent(href.slice(href.indexOf(",") + 1));
      const lines = csv.trim().split(/\r\n/);
      expect(lines[0]).toBe("Timer length,Title,Timer color");
      expect(lines).toHaveLength(3);
      expect(lines[1]).toContain("First example");
      expect(lines[2]).toContain("#F97316");
    }
    expect(captured[0]?.download).toMatch(/-example\.csv$/);
  } finally {
    click.mockRestore();
  }
});
