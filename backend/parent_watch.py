"""Run a command and kill it when the backend that started it dies.

Usage: python parent_watch.py <parent pid> -- <command...>

Used where Linux's prctl(PR_SET_PDEATHSIG) isn't available (macOS, Windows, or
MANIM_PARENT_WATCH=watcher). The executor starts this script in a new session
(POSIX) so the command shares its process group: cancel() still signals the
whole group, and when the parent disappears this script kills the group, or on
Windows the command's process tree. The command inherits stdin/stdout/stderr,
so its output reaches the backend unchanged. Exits with the command's code.
"""

import os
import signal
import subprocess
import sys

POLL_SECONDS = float(os.environ.get("MANIM_PARENT_WATCH_POLL", "0.5"))


def _parent_alive(parent_pid: int, started) -> bool:
    if os.name != "nt":
        # Reparented (to init or a subreaper) once the parent is gone.
        return os.getppid() == parent_pid
    try:
        import psutil
    except ImportError:
        return True  # can't tell; the backend's own cancel still works
    try:
        process = psutil.Process(parent_pid)
        return process.is_running() and (started is None or process.create_time() == started)
    except psutil.Error:
        return False


def _create_time(pid: int):
    if os.name != "nt":
        return None
    try:
        import psutil

        return psutil.Process(pid).create_time()
    except Exception:
        return None


def _kill(child: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(child.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    try:
        os.killpg(os.getpgrp(), signal.SIGKILL)  # the command, its children, and this script
    except OSError:
        child.kill()


def _restore_signals() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def main(argv: list) -> int:
    if len(argv) < 4 or argv[2] != "--":
        print("usage: parent_watch.py <parent pid> -- <command...>", file=sys.stderr)
        return 2
    parent_pid = int(argv[1])
    started = _create_time(parent_pid)
    if not _parent_alive(parent_pid, started):
        return 1
    kwargs = {}
    if os.name != "nt":
        # cancel() signals the whole group; the command gets it directly, and this
        # script stays to report the command's exit code.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        kwargs["preexec_fn"] = _restore_signals
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    child = subprocess.Popen(argv[3:], **kwargs)
    while True:
        try:
            return child.wait(timeout=POLL_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        if not _parent_alive(parent_pid, started):
            _kill(child)
            return 137


if __name__ == "__main__":
    sys.exit(main(sys.argv))
