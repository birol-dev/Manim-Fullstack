import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AIConnection } from "./api";
import { ConnectionDialog } from "./ConnectionDialog";
import {
  buildSetupPrompt,
  claudeCodeCommand,
  codexConfig,
  httpConfig,
  mcpConfig,
  SETUP_APP_KEY,
  tomlString,
  vsCodeConfig,
} from "./connection";
import { installFakeStudio, type FakeStudio } from "./test/fakeStudio";

const COMMAND = String.raw`C:\Program Files\Manim Studio\manim-studio.exe`;
const TOKEN_FILE = String.raw`C:\Users\Omer B\AppData\Local\Manim Studio\token.txt`;
const STDIO = { command: COMMAND, args: ["--token-file", TOKEN_FILE], background: true };
const DESKTOP: AIConnection = { available: true, url: "http://127.0.0.1:8123/mcp/", token: "secret-token", stdio: STDIO };
const DEV: AIConnection = { ...DESKTOP, stdio: { ...STDIO, background: false } };
const LEGACY: AIConnection = { available: true, url: "http://127.0.0.1:8123/mcp/", token: "secret-token" };

let studio: FakeStudio;

beforeEach(() => {
  studio = installFakeStudio();
});

function serve(connection: unknown) {
  studio.reply = (call) => call.path === "/api/studio/connection" ? { status: 200, body: connection } : null;
}

async function open(connection: unknown) {
  serve(connection);
  render(<ConnectionDialog onClose={() => {}} />);
  return screen.findByRole("button", { name: "Copy setup prompt" });
}

function codeCard(label: string) {
  const card = screen.getByRole("textbox", { name: label }).closest(".studio-code-card");
  if (!card) throw new Error(`No code card for ${label}`);
  return card as HTMLElement;
}

describe("ConnectionDialog", () => {
  it("puts the stdio command for every app in the prompt and leaves the token out", async () => {
    const user = userEvent.setup();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    await open(DESKTOP);
    await user.click(screen.getByRole("button", { name: "Copy setup prompt" }));
    const prompt = clipboard.mock.calls[0][0];

    expect(prompt).toContain("Manim Studio is a video app");
    expect(prompt).toContain(mcpConfig(DESKTOP));
    expect(prompt).toContain(claudeCodeCommand(DESKTOP));
    expect(prompt).toContain(vsCodeConfig(DESKTOP));
    expect(prompt).toContain(codexConfig(DESKTOP));
    expect(prompt).toContain("Settings → Developer → Edit Config");
    expect(prompt).toContain(".vscode/mcp.json");
    expect(prompt).toContain("~/.codex/config.toml");
    expect(prompt).toContain("If you can edit your own MCP settings, add it yourself. Otherwise, tell me exactly where to paste it.");
    expect(prompt).toContain("call the `guide` tool first");
    // The Claude Code line keeps the path as typed; JSON and TOML escape its backslashes.
    const escaped = JSON.stringify(COMMAND).slice(1, -1);
    expect(prompt.split(COMMAND)).toHaveLength(2);
    expect(prompt.split(escaped)).toHaveLength(4);
    expect(prompt).not.toContain("secret-token");
    expect(prompt).not.toContain("Bearer");
  });

  it("escapes Windows paths with spaces and backslashes in JSON, TOML and Claude Code", () => {
    const json = mcpConfig(DESKTOP);
    expect(JSON.parse(json).mcpServers["manim-studio"]).toEqual({ command: COMMAND, args: ["--token-file", TOKEN_FILE] });
    expect(json).toContain(String.raw`"C:\\Program Files\\Manim Studio\\manim-studio.exe"`);
    expect(json).toContain(String.raw`"C:\\Users\\Omer B\\AppData\\Local\\Manim Studio\\token.txt"`);
    expect(vsCodeConfig(DESKTOP)).toContain(String.raw`"C:\\Program Files\\Manim Studio\\manim-studio.exe"`);

    const toml = codexConfig(DESKTOP);
    expect(toml).toContain(String.raw`command = "C:\\Program Files\\Manim Studio\\manim-studio.exe"`);
    expect(toml).toContain(String.raw`args = ["--token-file", "C:\\Users\\Omer B\\AppData\\Local\\Manim Studio\\token.txt"]`);
    expect(toml).not.toContain(String.raw`"C:\Program`);
    expect(tomlString(String.raw`C:\A "quoted" path`)).toBe(String.raw`"C:\\A \"quoted\" path"`);

    expect(claudeCodeCommand(DESKTOP)).toBe(String.raw`claude mcp add manim-studio -- "C:\Program Files\Manim Studio\manim-studio.exe" --token-file "C:\Users\Omer B\AppData\Local\Manim Studio\token.txt"`);
  });

  it("falls back to the web address and token when the server has no stdio command", async () => {
    const user = userEvent.setup();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    await open(LEGACY);
    expect(screen.queryByRole("combobox", { name: "Your AI app" })).not.toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
    const steps = within(screen.getByRole("list")).getAllByRole("listitem").map((item) => item.textContent);
    expect(steps).toEqual([
      "Copy the settings.",
      "Paste them into your AI app's MCP settings.",
      "Keep Manim Studio open while you use it.",
    ]);
    expect(screen.getByRole("textbox", { name: "MCP configuration" })).toHaveTextContent("Bearer secr•••");
    expect(screen.getByText("Keep Manim Studio open while you use it.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Copy setup prompt" }));
    const prompt = clipboard.mock.calls[0][0];
    expect(prompt).toContain(httpConfig(LEGACY));
    expect(prompt).toContain('"url": "http://127.0.0.1:8123/mcp/"');
    expect(prompt).toContain('"Authorization": "Bearer secret-token"');
    expect(prompt).toContain("claude mcp add --transport http manim-studio http://127.0.0.1:8123/mcp/");
    expect(prompt).not.toContain("--token-file");
  });

  it("says whether Manim Studio can stay closed", async () => {
    await open(DESKTOP);
    expect(screen.getByText("Works even when Manim Studio is closed. Your AI app starts it in the background.")).toBeInTheDocument();
    expect(screen.queryByText("Keep Manim Studio open while your AI uses it.")).not.toBeInTheDocument();

    cleanup();
    await open(DEV);
    expect(screen.getByText("Keep Manim Studio open while your AI uses it.")).toBeInTheDocument();
    expect(screen.queryByText(/Works even when Manim Studio is closed/)).not.toBeInTheDocument();
  });

  it("marks the background note with role=note", async () => {
    await open(DESKTOP);
    expect(screen.getByRole("note")).toHaveTextContent("Works even when Manim Studio is closed. Your AI app starts it in the background.");

    cleanup();
    await open(DEV);
    expect(screen.getByRole("note")).toHaveTextContent("Keep Manim Studio open while your AI uses it.");
  });

  it("drops the numbered steps and offers a self-setup section when the app can start Studio", async () => {
    await open(DESKTOP);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByText("Copy the setup prompt.")).not.toBeInTheDocument();
    expect(screen.getByText("Paste it into your AI assistant's chat. It sets up the connection, or tells you where to paste it.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Or set it up yourself" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Your AI app" })).toBeInTheDocument();
  });

  it("switches the snippet with the app picker and remembers the choice", async () => {
    const user = userEvent.setup();
    await open(DESKTOP);
    const picker = screen.getByRole("combobox", { name: "Your AI app" });
    expect(picker).toHaveValue("claude-desktop");
    expect(screen.getByRole("textbox", { name: "Claude Desktop configuration" }).textContent).toBe(mcpConfig(DESKTOP));

    await user.selectOptions(picker, "codex");
    expect(screen.getByRole("textbox", { name: "Codex configuration" }).textContent).toBe(codexConfig(DESKTOP));
    expect(localStorage.getItem(SETUP_APP_KEY)).toBe("codex");

    await user.selectOptions(picker, "claude-code");
    expect(screen.getByRole("textbox", { name: "Claude Code configuration" }).textContent).toBe(claudeCodeCommand(DESKTOP));
    expect(localStorage.getItem(SETUP_APP_KEY)).toBe("claude-code");

    cleanup();
    serve(DESKTOP);
    render(<ConnectionDialog onClose={() => {}} />);
    expect(await screen.findByRole("combobox", { name: "Your AI app" })).toHaveValue("claude-code");
    expect(screen.getByRole("textbox", { name: "Claude Code configuration" }).textContent).toBe(claudeCodeCommand(DESKTOP));
  });

  it("copies the prompt, the chosen app's snippet and the web address settings", async () => {
    const user = userEvent.setup();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    await open(DESKTOP);

    await user.click(screen.getByRole("button", { name: "Copy setup prompt" }));
    expect(clipboard).toHaveBeenLastCalledWith(buildSetupPrompt(DESKTOP));
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "Your AI app" }), "vscode");
    await user.click(within(codeCard("VS Code configuration")).getByRole("button", { name: "Copy" }));
    expect(clipboard).toHaveBeenLastCalledWith(vsCodeConfig(DESKTOP));

    await user.click(screen.getByRole("button", { name: "Copy configuration" }));
    expect(clipboard).toHaveBeenLastCalledWith(httpConfig(DESKTOP));
    expect(screen.getByRole("textbox", { name: "Web address configuration" })).toHaveTextContent("Bearer secr•••");
  });

  it("keeps the web address token hidden until Show is pressed", async () => {
    const user = userEvent.setup();
    await open(DESKTOP);
    expect(screen.getByText("Connect by web address").closest("details")).not.toHaveAttribute("open");
    const web = screen.getByRole("textbox", { name: "Web address configuration" });
    expect(web).toHaveTextContent("Bearer secr•••");
    expect(web).not.toHaveTextContent("secret-token");

    await user.click(screen.getByRole("button", { name: "Show token" }));
    expect(web).toHaveTextContent("Bearer secret-token");
    await user.click(screen.getByRole("button", { name: "Hide token" }));
    expect(web).not.toHaveTextContent("secret-token");
  });

  it("shows how to copy by hand when the clipboard is unavailable", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("Not allowed"));
    await open(DEV);
    await user.click(screen.getByRole("button", { name: "Copy setup prompt" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't copy automatically");
  });
});
