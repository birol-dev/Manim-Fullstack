/** Text the connection dialog shows and copies: MCP snippets and a setup prompt for AI assistants. */
import type { AIConnection } from "./api";

export type SetupApp = "claude-desktop" | "claude-code" | "cursor" | "vscode" | "codex" | "other";

export interface SetupAppInfo {
  id: SetupApp;
  label: string;
  /** Where this app's snippet goes, in one sentence. */
  where: string;
}

export const SETUP_APPS: SetupAppInfo[] = [
  { id: "claude-desktop", label: "Claude Desktop", where: "In Claude Desktop, open Settings → Developer → Edit Config, paste this in, then restart the app." },
  { id: "claude-code", label: "Claude Code", where: "Run this command in your terminal." },
  { id: "cursor", label: "Cursor", where: "In Cursor, open Settings → MCP → Add new MCP server, or edit ~/.cursor/mcp.json." },
  { id: "vscode", label: "VS Code", where: "Save this as .vscode/mcp.json in your project." },
  { id: "codex", label: "Codex", where: "Add this to ~/.codex/config.toml." },
  { id: "other", label: "Other", where: "Paste this into your AI app's MCP settings." },
];

/** Where the dialog remembers the last chosen app (localStorage, best effort). */
export const SETUP_APP_KEY = "manim-studio:setup-app";

const SERVER = "manim-studio";
const bearer = (token: string) => `Bearer ${token}`;

export function readSetupApp(): SetupApp {
  try {
    const stored = localStorage.getItem(SETUP_APP_KEY);
    return SETUP_APPS.some((app) => app.id === stored) ? stored as SetupApp : "claude-desktop";
  } catch {
    return "claude-desktop";
  }
}

export function rememberSetupApp(app: SetupApp) {
  try {
    localStorage.setItem(SETUP_APP_KEY, app);
  } catch {
    // Private windows and locked-down browsers simply forget the choice.
  }
}

export function appInfo(app: SetupApp): SetupAppInfo {
  return SETUP_APPS.find((item) => item.id === app) ?? SETUP_APPS[0];
}

/** The JSON every MCP app understands: a command line when we have one, otherwise the web address. */
export function mcpConfig(connection: AIConnection): string {
  const stdio = connection.stdio;
  const server = stdio
    ? { command: stdio.command, args: stdio.args }
    : { url: connection.url, headers: { Authorization: bearer(connection.token) } };
  return JSON.stringify({ mcpServers: { [SERVER]: server } }, null, 2);
}

/** VS Code uses "servers" and an explicit transport type. */
export function vsCodeConfig(connection: AIConnection): string {
  const stdio = connection.stdio;
  const server = stdio
    ? { type: "stdio", command: stdio.command, args: stdio.args }
    : { type: "http", url: connection.url, headers: { Authorization: bearer(connection.token) } };
  return JSON.stringify({ servers: { [SERVER]: server } }, null, 2);
}

/** A TOML basic string: backslashes must be doubled inside Windows paths. */
export function tomlString(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

export function codexConfig(connection: AIConnection): string {
  const stdio = connection.stdio;
  if (stdio) {
    const args = stdio.args.map(tomlString).join(", ");
    return `[mcp_servers.${SERVER}]\ncommand = ${tomlString(stdio.command)}\nargs = [${args}]`;
  }
  return `[mcp_servers.${SERVER}]\nurl = ${tomlString(connection.url)}\nhttp_headers = { Authorization = ${tomlString(bearer(connection.token))} }`;
}

const SHELL_SAFE = /^[A-Za-z0-9_\-.:/\\=,+@%]+$/;

/** cmd.exe, PowerShell and POSIX shells all accept a double-quoted path and keep its backslashes. */
export function shellArg(value: string): string {
  if (SHELL_SAFE.test(value)) return value;
  return `"${value.replace(/"/g, '\\"')}"`;
}

export function claudeCodeCommand(connection: AIConnection): string {
  const stdio = connection.stdio;
  const parts = stdio
    ? ["claude", "mcp", "add", SERVER, "--", stdio.command, ...stdio.args]
    : ["claude", "mcp", "add", "--transport", "http", SERVER, connection.url, "--header", `Authorization: ${bearer(connection.token)}`];
  return parts.map(shellArg).join(" ");
}

/** What the dialog's code card shows for one app. */
export function appSnippet(app: SetupApp, connection: AIConnection): string {
  switch (app) {
    case "claude-code":
      return claudeCodeCommand(connection);
    case "vscode":
      return vsCodeConfig(connection);
    case "codex":
      return codexConfig(connection);
    default:
      return mcpConfig(connection);
  }
}

/** The web address alternative, always with the real token (the card masks it on screen). */
export function httpConfig(connection: AIConnection): string {
  return mcpConfig({ ...connection, stdio: null });
}

/** A message the person pastes into any AI assistant: what we are and how to connect to every common app. */
export function buildSetupPrompt(connection: AIConnection): string {
  const config = mcpConfig(connection);
  const stdio = connection.stdio;
  const keepOpen = stdio?.background
    ? "This works even when Manim Studio is closed: you start its server in the background (the first call can take half a minute)."
    : "Manim Studio needs to stay open while you use it.";
  return [
    "Manim Studio is a video app, and you can make and edit videos in it for me through its MCP server.",
    "",
    "Add the Manim Studio MCP server to your settings:",
    "",
    "Claude Desktop and Cursor — add this to your MCP settings:",
    config,
    "In Claude Desktop, open Settings → Developer → Edit Config, paste this in, then restart the app.",
    "",
    "Claude Code — run this command:",
    claudeCodeCommand(connection),
    "",
    "VS Code — save this as .vscode/mcp.json:",
    vsCodeConfig(connection),
    "",
    "Codex — add this to ~/.codex/config.toml:",
    codexConfig(connection),
    "",
    "Any other MCP app — use the same JSON as for Claude Desktop.",
    "",
    "If you can edit your own MCP settings, add it yourself. Otherwise, tell me exactly where to paste it.",
    keepOpen,
    "",
    "Once you're connected, call the `guide` tool first, then help me make a video.",
  ].join("\n");
}
