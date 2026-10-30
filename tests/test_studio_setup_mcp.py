"""Connecting AI assistants' MCP settings: the entry, the safety, and the routes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import main
from studio import api as api_module
from studio import service as service_module
from studio import setup_mcp
from studio.auth import agent_token
from studio.setup_mcp import ConfigError, McpSetup, UnknownApp
from tests.conftest import LocalClient
from tests.studio_fakes import make_service

CONNECTION = {
    "stdio": {"command": "/opt/manim/python", "args": ["-B", "/opt/manim/mcp_server.py",
                                                       "--desktop-data", "/home/ana/Data"]},
    "url": "http://127.0.0.1:8000/mcp/",
    "token": "secret-agent-token",
}
MOVED = {
    "stdio": {"command": "/Applications/Manim Studio/python", "args": ["-B", "/Applications/Manim Studio/mcp_server.py",
                                                                       "--desktop-data", "/home/ana/Data"]},
    "url": "http://127.0.0.1:8000/mcp/",
    "token": "secret-agent-token",
}


def make_setup(tmp_path, platform="linux", **kwargs):
    return McpSetup(home=str(tmp_path), appdata=str(tmp_path / "appdata"),
                    localappdata=str(tmp_path / "localappdata"), platform=platform,
                    which=lambda _name: None, **kwargs)


def read_json(path):
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as target:
        json.dump(value, target)


# --------------------------------------------------------------------------- #
# Paths per OS
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("platform", ["windows", "macos", "linux"])
def test_each_os_has_a_config_path_for_every_app(tmp_path, platform):
    setup = make_setup(tmp_path, platform)
    paths = setup.paths()
    assert list(paths) == ["claude-desktop", "claude-code", "cursor", "vscode", "windsurf", "codex", "gemini-cli"]
    home = str(tmp_path)
    expected = {
        "claude-code": os.path.join(home, ".claude.json"),
        "cursor": os.path.join(home, ".cursor", "mcp.json"),
        "windsurf": os.path.join(home, ".codeium", "windsurf", "mcp_config.json"),
        "codex": os.path.join(home, ".codex", "config.toml"),
        "gemini-cli": os.path.join(home, ".gemini", "settings.json"),
    }
    if platform == "windows":
        expected["claude-desktop"] = os.path.join(home, "appdata", "Claude", "claude_desktop_config.json")
        expected["vscode"] = os.path.join(home, "appdata", "Code", "User", "mcp.json")
    elif platform == "macos":
        support = os.path.join(home, "Library", "Application Support")
        expected["claude-desktop"] = os.path.join(support, "Claude", "claude_desktop_config.json")
        expected["vscode"] = os.path.join(support, "Code", "User", "mcp.json")
    else:
        expected["claude-desktop"] = os.path.join(home, ".config", "Claude", "claude_desktop_config.json")
        expected["vscode"] = os.path.join(home, ".config", "Code", "User", "mcp.json")
    for app_id, path in expected.items():
        assert setup.paths()[app_id]["config"] == path
    assert paths["codex"]["kind"] == "toml"
    assert paths["vscode"]["key"] == "servers"
    assert paths["cursor"]["key"] == "mcpServers"


def test_the_store_version_of_claude_uses_its_packaged_folder(tmp_path):
    setup = make_setup(tmp_path, "windows")
    package = tmp_path / "localappdata" / "Packages" / "Claude_12345"
    (package / "LocalCache" / "Roaming" / "Claude").mkdir(parents=True)
    store_folder = tmp_path / "appdata" / "Claude"
    store_folder.mkdir(parents=True)

    assert setup.paths()["claude-desktop"]["config"] == str(
        package / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
    setup.connect("claude-desktop", CONNECTION)

    packaged = package / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
    assert json.loads(packaged.read_text(encoding="utf-8"))["mcpServers"]["manim-studio"]["command"] == \
        "/opt/manim/python"
    assert not (store_folder / "claude_desktop_config.json").exists()


# --------------------------------------------------------------------------- #
# JSON editing
# --------------------------------------------------------------------------- #


def test_a_new_file_is_created_with_only_our_server(tmp_path):
    setup = make_setup(tmp_path)
    result = setup.connect("claude-code", CONNECTION)

    assert result["connected"] and not result["needs_repair"] and result["error"] is None
    path = tmp_path / ".claude.json"
    data = read_json(path)
    assert data == {"mcpServers": {"manim-studio": {
        "command": "/opt/manim/python",
        "args": ["-B", "/opt/manim/mcp_server.py", "--desktop-data", "/home/ana/Data"]}}}
    assert not (tmp_path / ".claude.json.manim-studio.bak").exists()


def test_a_config_far_above_the_old_limit_is_read_and_other_keys_kept(tmp_path):
    """~/.claude.json keeps project history and commonly passes 4 MB; it is still a config."""
    setup = make_setup(tmp_path)
    path = tmp_path / ".claude.json"
    filler = "x" * (5 * 1024 * 1024)
    write_json(path, {"projects": {"/home/ana/app": {"history": filler}},
                      "mcpServers": {"other": {"command": "other", "args": ["x"]}}})
    assert path.stat().st_size > 4 * 1024 * 1024

    result = setup.connect("claude-code", CONNECTION)

    assert result["connected"] is True and result["error"] is None
    data = read_json(path)
    assert data["projects"]["/home/ana/app"]["history"] == filler
    assert data["mcpServers"]["other"] == {"command": "other", "args": ["x"]}
    assert data["mcpServers"]["manim-studio"]["command"] == "/opt/manim/python"


def test_other_servers_keys_and_order_are_kept(tmp_path):
    setup = make_setup(tmp_path)
    path = tmp_path / ".claude.json"
    write_json(path, {"theme": "dark", "mcpServers": {"other": {"command": "other", "args": ["x"]}},
                      "unknown": [1, 2]})

    setup.connect("claude-code", CONNECTION)

    data = read_json(path)
    assert list(data) == ["theme", "mcpServers", "unknown"]
    assert list(data["mcpServers"]) == ["other", "manim-studio"]
    assert data["mcpServers"]["other"] == {"command": "other", "args": ["x"]}
    assert data["unknown"] == [1, 2]


def test_a_damaged_file_is_refused_and_untouched(tmp_path):
    setup = make_setup(tmp_path)
    path = tmp_path / ".cursor" / "mcp.json"
    os.makedirs(path.parent)
    path.write_bytes(b"{not json")
    before = path.read_bytes()

    with pytest.raises(ConfigError) as info:
        setup.connect("cursor", CONNECTION)
    assert "damaged" in str(info.value)
    assert path.read_bytes() == before
    assert not (path.parent / "mcp.json.manim-studio.bak").exists()

    entry = next(item for item in setup.entries(CONNECTION) if item["id"] == "cursor")
    assert entry["connected"] is False and "damaged" in entry["error"]
    assert "secret-agent-token" not in json.dumps(entry)


def test_the_first_backup_is_kept_and_never_overwritten(tmp_path):
    setup = make_setup(tmp_path)
    path = tmp_path / ".claude.json"
    original = {"mcpServers": {"other": {"command": "other", "args": []}}}
    write_json(path, original)
    first_bytes = path.read_bytes()

    setup.connect("claude-code", CONNECTION)
    setup.connect("claude-code", CONNECTION)
    setup.connect("claude-code", MOVED)

    backup = tmp_path / ".claude.json.manim-studio.bak"
    assert backup.read_bytes() == first_bytes
    assert read_json(backup) == original
    assert read_json(path)["mcpServers"]["manim-studio"]["command"] == "/Applications/Manim Studio/python"


def test_vscode_servers_need_a_type_and_use_the_same_entry(tmp_path):
    setup = make_setup(tmp_path)
    setup.connect("vscode", CONNECTION)
    entry = read_json(tmp_path / ".config" / "Code" / "User" / "mcp.json")["servers"]["manim-studio"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "/opt/manim/python"


def test_remote_connection_uses_url_and_bearer_header_without_leaking_the_token(tmp_path):
    setup = make_setup(tmp_path)
    connection = {"stdio": None, "url": "http://127.0.0.1:8000/mcp/", "token": "secret-agent-token"}
    result = setup.connect("cursor", connection)

    entry = read_json(tmp_path / ".cursor" / "mcp.json")["mcpServers"]["manim-studio"]
    assert entry == {"url": "http://127.0.0.1:8000/mcp/",
                     "headers": {"Authorization": "Bearer secret-agent-token"}}
    assert "secret-agent-token" not in json.dumps(setup.entries(connection))
    assert "secret-agent-token" not in json.dumps(result)


def test_disconnect_removes_only_our_entry(tmp_path):
    setup = make_setup(tmp_path)
    path = tmp_path / ".claude.json"
    write_json(path, {"mcpServers": {"other": {"command": "other", "args": []}}})
    setup.connect("claude-code", CONNECTION)

    result = setup.disconnect("claude-code", CONNECTION)

    assert result["connected"] is False
    assert read_json(path) == {"mcpServers": {"other": {"command": "other", "args": []}}}
    assert setup.disconnect("claude-code", CONNECTION)["connected"] is False


def test_a_symlinked_config_keeps_its_link(tmp_path):
    real = tmp_path / "real-settings.json"
    real.write_text("{}\n", encoding="utf-8")
    link = tmp_path / ".claude.json"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")

    make_setup(tmp_path).connect("claude-code", CONNECTION)

    assert os.path.islink(link)
    assert read_json(real)["mcpServers"]["manim-studio"]["command"] == "/opt/manim/python"


def test_unknown_app_is_a_plain_404(tmp_path):
    with pytest.raises(UnknownApp) as info:
        make_setup(tmp_path).connect("notepad", CONNECTION)
    assert info.value.status == 404


# --------------------------------------------------------------------------- #
# Codex TOML
# --------------------------------------------------------------------------- #


CODEX = """# my own settings
model = "o3"

[mcp_servers.other]
command = "other-server"
args = ["--quiet"]

# math help
[profiles.fast]
model = "tiny"
"""


def test_codex_keeps_every_other_byte(tmp_path):
    setup = make_setup(tmp_path)
    path = tmp_path / ".codex" / "config.toml"
    os.makedirs(path.parent)
    path.write_text(CODEX, encoding="utf-8")

    setup.connect("codex", CONNECTION)

    text = path.read_text(encoding="utf-8")
    assert "# my own settings" in text
    assert '# math help\n[profiles.fast]\nmodel = "tiny"' in text
    assert '[mcp_servers.other]\ncommand = "other-server"\nargs = ["--quiet"]' in text
    import tomllib

    data = tomllib.loads(text)
    assert data["mcp_servers"]["manim-studio"]["command"] == "/opt/manim/python"
    assert data["mcp_servers"]["manim-studio"]["args"][0] == "-B"
    assert data["mcp_servers"]["other"]["command"] == "other-server"


def test_codex_disconnect_removes_only_our_table(tmp_path):
    setup = make_setup(tmp_path)
    path = tmp_path / ".codex" / "config.toml"
    os.makedirs(path.parent)
    path.write_text(CODEX, encoding="utf-8")
    setup.connect("codex", CONNECTION)

    setup.disconnect("codex", CONNECTION)

    text = path.read_text(encoding="utf-8")
    assert "manim-studio" not in text
    assert '[mcp_servers.other]\ncommand = "other-server"\nargs = ["--quiet"]' in text
    assert '# math help\n[profiles.fast]\nmodel = "tiny"' in text


def test_codex_damaged_toml_is_refused_and_untouched(tmp_path):
    setup = make_setup(tmp_path)
    path = tmp_path / ".codex" / "config.toml"
    os.makedirs(path.parent)
    before = b"model = [not toml\n"
    path.write_bytes(before)

    with pytest.raises(ConfigError):
        setup.connect("codex", CONNECTION)
    assert path.read_bytes() == before


# --------------------------------------------------------------------------- #
# Repair
# --------------------------------------------------------------------------- #


def test_repair_rewrites_a_stale_entry_only(tmp_path):
    setup = make_setup(tmp_path)
    setup.connect("cursor", CONNECTION)
    assert not next(item for item in setup.entries(CONNECTION) if item["id"] == "cursor")["needs_repair"]

    stale = next(item for item in setup.entries(MOVED) if item["id"] == "cursor")
    assert stale["needs_repair"] is True

    setup.repair_all(MOVED)

    repaired = next(item for item in setup.entries(MOVED) if item["id"] == "cursor")
    assert repaired["needs_repair"] is False
    entry = read_json(tmp_path / ".cursor" / "mcp.json")["mcpServers"]["manim-studio"]
    assert entry["command"] == "/Applications/Manim Studio/python"


def test_repair_never_adds_a_connection(tmp_path):
    setup = make_setup(tmp_path)
    setup.repair_all(CONNECTION)
    assert not (tmp_path / ".cursor" / "mcp.json").exists()
    assert not (tmp_path / ".claude.json").exists()
    assert all(not item["connected"] for item in setup.entries(CONNECTION))


def test_detection_uses_the_app_folder_or_the_claude_command(tmp_path):
    setup = make_setup(tmp_path)
    assert not next(item for item in setup.entries(CONNECTION) if item["id"] == "cursor")["detected"]
    (tmp_path / ".cursor").mkdir()
    assert next(item for item in setup.entries(CONNECTION) if item["id"] == "cursor")["detected"]

    cli = McpSetup(home=str(tmp_path), appdata=str(tmp_path / "appdata"),
                   localappdata=str(tmp_path / "localappdata"), platform="linux",
                   which=lambda name: "/usr/local/bin/claude" if name == "claude" else None)
    assert next(item for item in cli.entries(CONNECTION) if item["id"] == "claude-code")["detected"]


# --------------------------------------------------------------------------- #
# The published connection record
# --------------------------------------------------------------------------- #


def test_the_stdio_record_has_the_desktop_command(monkeypatch, tmp_path):
    workspace, app_root = tmp_path / "data" / "workspace", tmp_path / "app"
    monkeypatch.setenv("MANIM_API_TOKEN", "desktop-secret")
    monkeypatch.setenv("MANIM_WORKSPACE", str(workspace))

    record = setup_mcp.stdio_record(str(workspace), str(app_root))

    assert record == {
        "command": os.path.abspath(sys.executable),
        "args": ["-B", os.path.join(str(app_root), "backend", "studio", "mcp_server.py"),
                 "--desktop-data", str(tmp_path / "data")],
        "background": True,
    }


def test_the_stdio_record_has_the_source_command(monkeypatch, tmp_path):
    workspace, app_root = tmp_path / "workspace", tmp_path / "app"
    monkeypatch.delenv("MANIM_API_TOKEN", raising=False)
    monkeypatch.delenv("MANIM_WORKSPACE", raising=False)

    record = setup_mcp.stdio_record(str(workspace), str(app_root), "http://127.0.0.1:8123")

    assert record == {
        "command": os.path.abspath(sys.executable),
        "args": [os.path.join(str(app_root), "backend", "studio", "mcp_server.py"),
                 "--url", "http://127.0.0.1:8123",
                 "--token-file", os.path.join(str(workspace), "studio", "mcp-token")],
        "background": False,
    }


def test_the_connection_record_is_the_one_the_endpoint_publishes(monkeypatch, tmp_path):
    workspace, app_root = tmp_path / "workspace", tmp_path / "app"
    monkeypatch.delenv("MANIM_API_TOKEN", raising=False)
    monkeypatch.delenv("MANIM_WORKSPACE", raising=False)
    monkeypatch.delenv("MANIM_MCP_TOKEN", raising=False)

    record = setup_mcp.connection_record("http://localhost/", str(workspace), str(app_root), available=True)

    assert record["available"] is True
    assert record["url"] == "http://localhost/mcp/"
    assert record["token"] == agent_token(str(workspace))
    assert record["stdio"] == setup_mcp.stdio_record(str(workspace), str(app_root), "http://localhost/")


def test_repair_desktop_saves_the_published_stdio_record(monkeypatch, tmp_path):
    workspace, app_root = tmp_path / "data" / "workspace", tmp_path / "app"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("MANIM_API_TOKEN", "desktop-secret")
    monkeypatch.setenv("MANIM_WORKSPACE", str(workspace))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    path = tmp_path / ".claude.json"
    write_json(path, {"mcpServers": {
        "manim-studio": {"command": "/old/python", "args": ["-B", "/old/mcp_server.py"]},
        "other": {"command": "other", "args": []}}})

    setup_mcp.repair_desktop(str(workspace), str(app_root))

    published = setup_mcp.connection_record("http://localhost", str(workspace), str(app_root))["stdio"]
    data = read_json(path)
    assert data["mcpServers"]["manim-studio"] == {"command": published["command"], "args": published["args"]}
    assert data["mcpServers"]["other"] == {"command": "other", "args": []}


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@pytest.fixture
def studio(tmp_path, monkeypatch):
    svc, _ = make_service(tmp_path)
    monkeypatch.setattr(service_module, "service", svc)
    yield svc
    svc.shutdown_sync()


@pytest.fixture
def setup(tmp_path):
    return make_setup(tmp_path)


@pytest.fixture
def api(studio, setup, monkeypatch):
    monkeypatch.setattr(api_module, "connection_provider", lambda base_url: CONNECTION)
    monkeypatch.setattr(api_module, "get_setup_mcp", lambda: setup)
    return LocalClient(main.app, base_url="http://localhost")


def test_setup_mcp_routes_connect_and_disconnect(api, tmp_path):
    status = api.get("/api/studio/setup/status")
    assert status.status_code == 200
    apps = {item["id"]: item for item in status.json()["ai_apps"]}
    assert set(apps) == set(setup_mcp.APP_IDS)
    assert apps["cursor"]["connected"] is False

    connected = api.post("/api/studio/setup/ai-apps/cursor/connect")
    assert connected.status_code == 200
    assert connected.json()["connected"] is True
    assert "secret-agent-token" not in connected.text
    saved = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert saved["mcpServers"]["manim-studio"] == {
        "command": "/opt/manim/python",
        "args": ["-B", "/opt/manim/mcp_server.py", "--desktop-data", "/home/ana/Data"]}

    removed = api.delete("/api/studio/setup/ai-apps/cursor/connect")
    assert removed.status_code == 200 and removed.json()["connected"] is False
    assert json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8")) == {"mcpServers": {}}


def test_a_damaged_config_answers_409_with_a_plain_message(api, tmp_path):
    path = tmp_path / ".gemini" / "settings.json"
    os.makedirs(path.parent)
    path.write_text("{broken", encoding="utf-8")
    res = api.post("/api/studio/setup/ai-apps/gemini-cli/connect")
    assert res.status_code == 409
    assert "damaged" in res.json()["detail"]
    assert path.read_text(encoding="utf-8") == "{broken"


def test_setup_changes_are_refused_for_a_non_loopback_client(studio, monkeypatch, tmp_path):
    monkeypatch.setenv("MANIM_ALLOW_LAN", "1")
    monkeypatch.setattr(api_module, "connection_provider", lambda base_url: CONNECTION)
    monkeypatch.setattr(api_module, "get_setup_mcp", lambda: make_setup(tmp_path))
    client = LocalClient(main.app, base_url="http://127.0.0.1", client=("203.0.113.9", 5000))
    assert client.get("/api/studio/setup/status").status_code == 200
    assert client.post("/api/studio/setup/ai-apps/cursor/connect").status_code == 403
    assert client.delete("/api/studio/setup/ai-apps/cursor/connect").status_code == 403
    assert client.post("/api/studio/setup/components/ffmpeg/install").status_code == 403
    assert client.post("/api/studio/setup/reveal-data-folder").status_code == 403
    assert not (tmp_path / ".cursor" / "mcp.json").exists()


NO_SECOND_SERVER = r"""
import json
import os
import sys

sys.path.insert(0, sys.argv[1])
from fastapi.testclient import TestClient

import backend.main

# Home is moved after startup: on Windows, APPDATA decides where site-packages lives.
home = sys.argv[2]
os.environ["HOME"] = os.environ["USERPROFILE"] = home
os.environ["APPDATA"] = os.path.join(home, "appdata")
os.environ["LOCALAPPDATA"] = os.path.join(home, "localappdata")

client = TestClient(backend.main.app, base_url="http://localhost")
response = client.get("/api/studio/setup/status")
print(json.dumps({"status": response.status_code, "main_imported": "main" in sys.modules}))
"""


def test_setup_status_does_not_import_a_second_copy_of_the_server(tmp_path):
    """The app runs as backend.main; asking it for the connection must not import main."""
    root = Path(api_module.__file__).resolve().parents[2]
    workspace, home = tmp_path / "workspace", tmp_path / "home"
    workspace.mkdir()
    home.mkdir()
    env = {name: value for name, value in os.environ.items()
           if name not in ("MANIM_API_TOKEN", "MANIM_WORKSPACE", "MANIM_MCP_TOKEN")}
    env.update({"MANIM_WORKSPACE": str(workspace), "PYTHONIOENCODING": "utf-8"})

    done = subprocess.run([sys.executable, "-c", NO_SECOND_SERVER, str(root), str(home)],
                          cwd=str(root), env=env, capture_output=True, text=True, timeout=180)

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1]) == {"status": 200, "main_imported": False}
