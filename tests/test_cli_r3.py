"""Round 3 CLI: port validation (exit 2, no traceback), LAN warning, port-in-use check."""
import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import main

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "backend" / "main.py"


def _run_cli(*args, env=None, timeout=60):
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("MANIM_")}
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(MAIN), *args], capture_output=True, text=True, env=full_env, timeout=timeout, cwd=ROOT
    )


@pytest.mark.parametrize("value", ["abc", "0", "65536", "-1", "80.5", "", " ", "１２３", "1e3"])
def test_bad_port_flag_and_env_are_rejected(monkeypatch, value):
    monkeypatch.delenv("MANIM_PORT", raising=False)
    with pytest.raises(SystemExit) as info:
        main._cli_address(["--port", value])
    assert info.value.code == 2
    monkeypatch.setenv("MANIM_PORT", value)
    with pytest.raises(SystemExit) as info:
        main._cli_address([])
    assert info.value.code == 2


@pytest.mark.parametrize("value, port", [("1", 1), ("65535", 65535), (" 8100 ", 8100)])
def test_good_ports(monkeypatch, value, port):
    monkeypatch.setenv("MANIM_PORT", value)
    assert main._cli_address([])[1] == port
    assert main._cli_address(["--port", value])[1] == port


def test_flag_wins_over_a_bad_env(monkeypatch):
    monkeypatch.setenv("MANIM_PORT", "nope")
    assert main._cli_address(["--port", "9001"]) == ("127.0.0.1", 9001)


@pytest.mark.parametrize(
    "args, env, needle",
    [
        ((), {"MANIM_PORT": "abc"}, "MANIM_PORT='abc' is not a valid port"),
        (("--port", "70000"), {}, "argument --port: '70000' is not a valid port"),
    ],
)
def test_cli_process_exits_2_without_traceback(args, env, needle):
    proc = _run_cli(*args, env=env)
    assert proc.returncode == 2
    assert needle in proc.stderr
    assert "Traceback" not in proc.stderr


def test_lan_warning_wording_matches_run_py():
    sys.path.insert(0, str(ROOT))
    try:
        import run
    finally:
        sys.path.remove(str(ROOT))
    assert run.LAN_WARNING == main.LAN_WARNING
    assert "MANIM_ALLOW_LAN=1" in main.LAN_WARNING


@pytest.mark.parametrize("host, warned", [("0.0.0.0", True), ("192.168.1.5", True), ("::", True), ("127.0.0.1", False), ("localhost", False), ("::1", False)])
def test_cli_main_warns_for_non_loopback(capsys, host, warned):
    with patch.object(main, "_port_in_use", return_value=False), patch("uvicorn.run") as run:
        main._cli_main(["--host", host, "--port", "8123"])
    run.assert_called_once()
    assert run.call_args.kwargs == {"host": host, "port": 8123}
    assert (main.LAN_WARNING.strip() in capsys.readouterr().err) is warned


def test_cli_refuses_a_busy_port_before_starting_the_app(capsys):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        with patch("uvicorn.run") as run, pytest.raises(SystemExit) as info:
            main._cli_main(["--port", str(port)])
    assert info.value.code == 1
    run.assert_not_called()  # so the lifespan startup sweep never runs
    assert f"Port {port} is already in use" in capsys.readouterr().err


def test_port_in_use_probe():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert main._port_in_use("127.0.0.1", port)
        assert main._port_in_use("0.0.0.0", port)
    assert not main._port_in_use("127.0.0.1", port)
