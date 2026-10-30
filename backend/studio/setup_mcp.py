"""Connect AI assistants to this app, and repair their saved connection after a move.

Every app keeps its MCP servers in one settings file per OS (see ``McpSetup.paths``).
Only the entry named ``manim-studio`` is ever written: other servers, unknown keys,
key order and comments stay as they were. A file that cannot be parsed is left
untouched and answered with a plain message; a file is backed up once
(``<name>.manim-studio.bak``) before its first change and replaced atomically.
A symlinked config keeps its link: the file it points at is what changes.

    setup = McpSetup()
    setup.connect("cursor", connection)   # connection = connection_record(...)
    setup.repair_all(connection)          # desktop startup: fix stale commands only

``connection_record`` builds the record ``GET /api/studio/connection`` publishes: the
MCP address, this workspace's agent token, and the stdio command. The endpoint, the
setup routes and ``repair_desktop`` all build the stdio part through ``stdio_record``,
so a saved entry and a published one cannot drift. The record is the app's name and
command from ``stdio``; when there is no stdio command, apps that accept a remote
server get ``url`` + a bearer header instead. ``McpSetup`` never returns the token:
it stays inside the written file and never reaches a log line.
"""

from __future__ import annotations

import codecs
import glob
import json
import os
import re
import shutil
import sys
import tempfile
from typing import Optional

from .auth import agent_token
from .errors import StudioError
from .setup_components import mode_name

try:  # Python 3.11+; Codex is the only app that needs it.
    import tomllib
except ImportError:  # pragma: no cover - the app ships current Python builds
    tomllib = None

SERVER_NAME = "manim-studio"
# ~/.claude.json keeps the user's project history, so it grows far beyond a plain
# settings file (hundreds of MB on busy machines); anything under this is read.
MAX_CONFIG_BYTES = 128 * 1024 * 1024

APPS = (
    # id, label, restart hint
    ("claude-desktop", "Claude Desktop", "Restart Claude Desktop to finish."),
    ("claude-code", "Claude Code", "Start a new Claude Code session to finish."),
    ("cursor", "Cursor", "Restart Cursor to finish."),
    ("vscode", "Visual Studio Code", "Reload VS Code to finish."),
    ("windsurf", "Windsurf", "Restart Windsurf to finish."),
    ("codex", "Codex", "Start a new Codex session to finish."),
    ("gemini-cli", "Gemini CLI", "Start a new Gemini CLI session to finish."),
)
APP_IDS = tuple(app[0] for app in APPS)
APP_LABELS = {app[0]: app[1] for app in APPS}
RESTART_HINTS = {app[0]: app[2] for app in APPS}

# VS Code keeps servers under "servers" and needs a transport type; the rest use
# "mcpServers" with command/args and no type.
JSON_KEY = {
    "claude-desktop": "mcpServers",
    "claude-code": "mcpServers",
    "cursor": "mcpServers",
    "vscode": "servers",
    "windsurf": "mcpServers",
    "gemini-cli": "mcpServers",
}


class SetupError(StudioError):
    """Something in the setup step failed; the message is ready to show people."""

    status = 500


class ConfigError(SetupError):
    """The app's settings file exists but cannot be used, so nothing was written."""

    status = 409


class UnknownApp(SetupError):
    status = 404


def platform_name(value: Optional[str] = None) -> str:
    """``windows``, ``macos`` or ``linux`` (the names the setup API speaks)."""
    raw = (value or sys.platform).lower()
    if raw.startswith("win"):
        return "windows"
    if raw.startswith(("darwin", "mac")):
        return "macos"
    return "linux"


def _dotted(name: str) -> tuple:
    """Split a TOML table name on dots, keeping quoted parts together."""
    parts, buffer, quote = [], [], None
    for char in name:
        if quote:
            if char == quote:
                quote = None
            else:
                buffer.append(char)
        elif char in "\"'":
            quote = char
        elif char == ".":
            parts.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
    parts.append("".join(buffer).strip())
    return tuple(parts)


_HEADER = re.compile(r"^\s*\[\[?\s*([^\[\]]+?)\s*\]\]?\s*(?:#.*)?$")


def _header_name(line: str):
    match = _HEADER.match(line.rstrip("\r\n"))
    return _dotted(match.group(1)) if match else None


def _toml_value(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


class McpSetup:
    """Reads and writes one MCP entry per app; all paths are injectable for tests."""

    def __init__(self, *, home: Optional[str] = None, appdata: Optional[str] = None,
                 localappdata: Optional[str] = None, platform: Optional[str] = None,
                 which=None):
        self.home = os.path.abspath(home or os.path.expanduser("~"))
        self.appdata = os.path.abspath(appdata or os.environ.get("APPDATA")
                                       or os.path.join(self.home, "AppData", "Roaming"))
        self.localappdata = os.path.abspath(localappdata or os.environ.get("LOCALAPPDATA")
                                            or os.path.join(self.home, "AppData", "Local"))
        self.platform = platform_name(platform)
        self.which = which or shutil.which

    # -- where each app lives ------------------------------------------------------
    def _claude_dir(self) -> tuple:
        """The Claude folder and the folders that prove the app is installed."""
        if self.platform == "windows":
            packages = sorted(path for path in glob.glob(
                os.path.join(self.localappdata, "Packages", "Claude_*")) if os.path.isdir(path))
            if packages:
                # The Microsoft Store build sandboxes Roaming inside the package.
                return (os.path.join(packages[0], "LocalCache", "Roaming", "Claude"),
                        (packages[0], os.path.join(packages[0], "LocalCache", "Roaming", "Claude")))
            folder = os.path.join(self.appdata, "Claude")
        elif self.platform == "macos":
            folder = os.path.join(self.home, "Library", "Application Support", "Claude")
        else:
            folder = os.path.join(self.home, ".config", "Claude")
        return folder, (folder,)

    def _vscode_dir(self) -> str:
        if self.platform == "windows":
            return os.path.join(self.appdata, "Code", "User")
        if self.platform == "macos":
            return os.path.join(self.home, "Library", "Application Support", "Code", "User")
        return os.path.join(self.home, ".config", "Code", "User")

    def paths(self) -> dict:
        """``{app_id: {config, detect, kind, key}}`` for this OS."""
        claude, claude_evidence = self._claude_dir()
        vscode = self._vscode_dir()
        return {
            "claude-desktop": {
                "config": os.path.join(claude, "claude_desktop_config.json"),
                "detect": claude_evidence, "kind": "json", "key": JSON_KEY["claude-desktop"]},
            "claude-code": {
                "config": os.path.join(self.home, ".claude.json"),
                "detect": (os.path.join(self.home, ".claude.json"),),
                "kind": "json", "key": JSON_KEY["claude-code"]},
            "cursor": {
                "config": os.path.join(self.home, ".cursor", "mcp.json"),
                "detect": (os.path.join(self.home, ".cursor"),),
                "kind": "json", "key": JSON_KEY["cursor"]},
            "vscode": {
                "config": os.path.join(vscode, "mcp.json"),
                "detect": (vscode,), "kind": "json", "key": JSON_KEY["vscode"]},
            "windsurf": {
                "config": os.path.join(self.home, ".codeium", "windsurf", "mcp_config.json"),
                "detect": (os.path.join(self.home, ".codeium", "windsurf"),),
                "kind": "json", "key": JSON_KEY["windsurf"]},
            "codex": {
                "config": os.path.join(self.home, ".codex", "config.toml"),
                "detect": (os.path.join(self.home, ".codex"),), "kind": "toml", "key": "mcp_servers"},
            "gemini-cli": {
                "config": os.path.join(self.home, ".gemini", "settings.json"),
                "detect": (os.path.join(self.home, ".gemini"),),
                "kind": "json", "key": JSON_KEY["gemini-cli"]},
        }

    def _detected(self, app_id: str, info: dict) -> bool:
        if any(os.path.exists(path) for path in info["detect"]):
            return True
        return app_id == "claude-code" and bool(self.which("claude"))

    # -- the record we write --------------------------------------------------------------
    @staticmethod
    def _entry(app_id: str, connection: dict) -> dict:
        """The server entry for *app_id*, built from the app's live connection details."""
        connection = connection or {}
        stdio = connection.get("stdio")
        if isinstance(stdio, dict) and stdio.get("command"):
            entry = {"command": stdio["command"], "args": [str(item) for item in stdio.get("args") or []]}
            if app_id == "vscode":
                return {"type": "stdio", **entry}
            return entry
        url = connection.get("url")
        if not url:
            raise SetupError("The app connection is not ready yet. Try again.")
        headers = {"Authorization": f"Bearer {connection['token']}"} if connection.get("token") else {}
        if app_id == "vscode":
            return {"type": "http", "url": url, "headers": headers}
        return {"url": url, "headers": headers}

    @staticmethod
    def _needs_repair(existing, expected: dict) -> bool:
        if not isinstance(existing, dict):
            return True
        if "command" in expected:
            return (existing.get("command") != expected.get("command")
                    or existing.get("args") != expected.get("args"))
        return existing.get("url") != expected.get("url")

    # -- reading ------------------------------------------------------------------------
    @staticmethod
    def _read_bytes(path: str) -> Optional[bytes]:
        name = os.path.basename(path)
        if not os.path.isfile(path):
            return None
        try:
            size = os.path.getsize(path)
            if size > MAX_CONFIG_BYTES:
                raise ConfigError(f"The {name} file is too large to read safely. Nothing was changed.")
            with open(path, "rb") as source:
                return source.read(size + 1)
        except OSError:
            raise ConfigError(f"The {name} file could not be read. Nothing was changed.") from None

    def _read_json(self, path: str) -> tuple:
        name = os.path.basename(path)
        raw = self._read_bytes(path)
        if raw is None:
            return {}, None, False
        bom = raw.startswith(codecs.BOM_UTF8)
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            raise ConfigError(f"The {name} file is damaged, so it was left unchanged. "
                              "Fix or remove it, then try again.") from None
        if not isinstance(data, dict):
            raise ConfigError(f"The {name} file has an unexpected shape, so it was left unchanged.")
        return data, raw, bom

    def _json_existing(self, path: str, key: str):
        data, _raw, _bom = self._read_json(path)
        table = data.get(key)
        if table is None:
            return None
        if not isinstance(table, dict):
            name = os.path.basename(path)
            raise ConfigError(f'The {name} file has an unexpected "{key}" value, so it was left unchanged.')
        return table.get(SERVER_NAME)

    def _read_toml(self, path: str) -> tuple:
        name = os.path.basename(path)
        raw = self._read_bytes(path)
        if raw is None:
            return {}, None, ""
        if tomllib is None:
            raise ConfigError("This Python cannot read Codex settings.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ConfigError(f"The {name} file is damaged, so it was left unchanged.") from None
        try:
            data = tomllib.loads(text)
        except Exception:
            raise ConfigError(f"The {name} file is damaged, so it was left unchanged. "
                              "Fix or remove it, then try again.") from None
        return data, raw, text

    def _toml_existing(self, path: str):
        data, _raw, _text = self._read_toml(path)
        servers = data.get("mcp_servers")
        if servers is None:
            return None
        if not isinstance(servers, dict):
            name = os.path.basename(path)
            raise ConfigError(f'The {name} file has an unexpected "mcp_servers" value, so it was left unchanged.')
        return servers.get(SERVER_NAME)

    def _existing(self, app_id: str, info: dict):
        if not os.path.isfile(info["config"]):
            return None
        if info["kind"] == "toml":
            return self._toml_existing(info["config"])
        return self._json_existing(info["config"], info["key"])

    # -- writing -------------------------------------------------------------------
    @staticmethod
    def _backup(path: str) -> None:
        """Keep the first version of a config; never replace an existing backup."""
        backup = path + ".manim-studio.bak"
        if os.path.lexists(backup) or not os.path.exists(path):
            return
        name = os.path.basename(path)
        try:
            with open(path, "rb") as source:
                data = source.read()
        except OSError:
            raise ConfigError(f"The {name} file could not be read. Nothing was changed.") from None
        try:
            with open(backup, "xb") as target:
                target.write(data)
        except FileExistsError:
            pass
        except OSError:
            raise ConfigError(f"The {name} file could not be backed up. Nothing was changed.") from None

    @staticmethod
    def _replace(path: str, data: bytes) -> None:
        """Write a temp file next to the target and move it into place."""
        target = os.path.realpath(path) if os.path.islink(path) else os.path.abspath(path)
        folder = os.path.dirname(target)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            raise ConfigError(f"The folder for {os.path.basename(path)} could not be created.") from None
        fd, temp = tempfile.mkstemp(prefix=".manim-studio-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise ConfigError(f"{os.path.basename(path)} could not be saved. Nothing was changed.") from None

    def _save(self, path: str, data: bytes, original: Optional[bytes]) -> None:
        if data == original:
            return
        self._backup(path)
        self._replace(path, data)

    def _save_json(self, path: str, data: dict, original: Optional[bytes], bom: bool) -> None:
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        payload = text.encode("utf-8")
        self._save(path, codecs.BOM_UTF8 + payload if bom else payload, original)

    @staticmethod
    def _block(entry: dict) -> str:
        lines = [f"[mcp_servers.{SERVER_NAME}]"]
        for key in ("command", "args", "url"):
            if key in entry:
                lines.append(f"{key} = {_toml_value(entry[key])}")
        headers = entry.get("headers")
        if isinstance(headers, dict) and headers:
            lines.extend(["", f"[mcp_servers.{SERVER_NAME}.headers]"])
            lines.extend(f"{name} = {_toml_value(value)}" for name, value in headers.items())
        return "\n".join(lines) + "\n"

    def _write_toml(self, path: str, entry: Optional[dict]) -> None:
        """Insert, replace or remove only our table; all other text stays byte-for-byte."""
        _data, raw, text = self._read_toml(path)
        lines = text.splitlines(keepends=True)
        headers = [(index, _header_name(line)) for index, line in enumerate(lines)]
        headers = [(index, name) for index, name in headers if name is not None]
        ranges = []
        for position, (index, name) in enumerate(headers):
            if name[:2] != ("mcp_servers", SERVER_NAME):
                continue
            end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
            ranges.append([index, end])
        merged = []
        for start, end in ranges:
            if merged and merged[-1][1] == start:
                merged[-1][1] = end
            else:
                merged.append([start, end])

        if entry is None:
            for start, end in reversed(merged):
                del lines[start:end]
        else:
            block = self._block(entry).splitlines(keepends=True)
            if merged:
                lines[merged[0][0]:merged[0][1]] = block
                for start, end in reversed(merged[1:]):
                    del lines[start:end]
            else:
                if text and not text.endswith("\n"):
                    lines.append("\n")
                if text.strip():
                    lines.append("\n")
                lines.extend(block)
        new_text = "".join(lines)
        if tomllib is None:
            raise ConfigError("This Python cannot read Codex settings.")
        try:
            tomllib.loads(new_text)
        except Exception:
            raise ConfigError("The Codex settings could not be updated safely. Nothing was changed.") from None
        if new_text != text:
            self._save(path, new_text.encode("utf-8"), raw)

    def _connect(self, app_id: str, info: dict, entry: dict) -> None:
        path = info["config"]
        if info["kind"] == "toml":
            self._write_toml(path, entry)
            return
        data, raw, bom = self._read_json(path)
        table = data.get(info["key"])
        if table is None:
            table = data[info["key"]] = {}
        elif not isinstance(table, dict):
            name = os.path.basename(path)
            raise ConfigError(f'The {name} file has an unexpected "{info["key"]}" value, so it was left unchanged.')
        table[SERVER_NAME] = entry
        self._save_json(path, data, raw, bom)

    def _disconnect(self, app_id: str, info: dict) -> None:
        path = info["config"]
        if info["kind"] == "toml":
            self._write_toml(path, None)
            return
        if not os.path.isfile(path):
            return
        data, raw, bom = self._read_json(path)
        table = data.get(info["key"])
        if not isinstance(table, dict) or SERVER_NAME not in table:
            return
        del table[SERVER_NAME]
        self._save_json(path, data, raw, bom)

    # -- the public shape ------------------------------------------------------------
    def _info(self, app_id: str) -> dict:
        if app_id not in APP_IDS:
            raise UnknownApp("That app is not on the list.")
        return self.paths()[app_id]

    def inspect(self, app_id: str, connection: dict) -> dict:
        """One app's status; a damaged file becomes ``error`` instead of an exception."""
        info = self._info(app_id)
        result = {
            "id": app_id,
            "label": APP_LABELS[app_id],
            "detected": self._detected(app_id, info),
            "connected": False,
            "needs_repair": False,
            "restart_hint": None,
            "error": None,
        }
        try:
            existing = self._existing(app_id, info)
        except ConfigError as exc:
            result["error"] = str(exc)
            return result
        if existing is None:
            return result
        result["connected"] = True
        try:
            result["needs_repair"] = self._needs_repair(existing, self._entry(app_id, connection))
        except SetupError as exc:
            result["error"] = str(exc)
        result["restart_hint"] = RESTART_HINTS[app_id]
        return result

    def entries(self, connection: dict) -> list:
        """Every app in display order; a broken config never hides the others."""
        return [self.inspect(app_id, connection) for app_id in APP_IDS]

    def connect(self, app_id: str, connection: dict) -> dict:
        """Add or update our entry for *app_id* and return the app's new status."""
        info = self._info(app_id)
        self._connect(app_id, info, self._entry(app_id, connection))
        result = self.inspect(app_id, connection)
        if result["error"] is None:
            result["restart_hint"] = RESTART_HINTS[app_id]
        return result

    def disconnect(self, app_id: str, connection: Optional[dict] = None) -> dict:
        """Remove only our entry; the app keeps every other server."""
        info = self._info(app_id)
        self._disconnect(app_id, info)
        return self.inspect(app_id, connection or {})

    def repair_all(self, connection: dict) -> None:
        """Rewrite our stale entries; never add one and never raise."""
        for app_id in APP_IDS:
            try:
                info = self.paths()[app_id]
                existing = self._existing(app_id, info)
                if existing is not None and self._needs_repair(existing, self._entry(app_id, connection)):
                    self._connect(app_id, info, self._entry(app_id, connection))
            except Exception:  # noqa: BLE001 - startup repair must not break launch
                continue


def stdio_record(workspace_dir: str, app_root: str, base_url: str = "", python: Optional[str] = None,
                 desktop: Optional[bool] = None) -> dict:
    """The one stdio command clients run: the desktop app's own Python with its data
    folder, or, in a source checkout, the running server's address and token file."""
    desktop = mode_name() == "desktop" if desktop is None else desktop
    script = os.path.join(app_root, "backend", "studio", "mcp_server.py")
    command = os.path.abspath(python or sys.executable)
    if desktop:
        return {
            "command": command,
            "args": ["-B", script, "--desktop-data", os.path.dirname(os.path.abspath(workspace_dir))],
            "background": True,
        }
    return {
        "command": command,
        "args": [script, "--url", base_url,
                 "--token-file", os.path.join(os.path.abspath(workspace_dir), "studio", "mcp-token")],
        "background": False,
    }


def connection_record(base_url: str, workspace_dir: str, app_root: str, *, available: bool = False,
                      python: Optional[str] = None, desktop: Optional[bool] = None) -> dict:
    """The record ``GET /api/studio/connection`` publishes (and the setup routes read)."""
    return {
        "available": bool(available),
        "url": base_url.rstrip("/") + "/mcp/",
        "token": agent_token(workspace_dir),
        "stdio": stdio_record(workspace_dir, app_root, base_url, python=python, desktop=desktop),
    }


def repair_desktop(workspace_dir: str, app_root: str) -> None:
    """Fix saved client entries after an app update or move (desktop launch only)."""
    connection = {"stdio": stdio_record(workspace_dir, app_root, desktop=True), "url": None, "token": None}
    McpSetup().repair_all(connection)
