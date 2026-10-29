"""Produce an unsigned portable directory, not an installer. Run prepare.py first."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from prepare import DESKTOP, ROOT, RUNTIME, remove_generated, runtime_paths

# The stdio command in GET /api/studio/connection runs backend/studio/mcp_server.py,
# which looks for agent_host.py next to launcher.py in the packaged shell/ folder.
SHELL_FILES = ("launcher.py", "sidecar.py", "agent_host.py", "win_job.py")


def copy_shell(source: Path, destination: Path) -> None:
    """Copy the lifecycle host and the stdio agent host into the packaged shell folder."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in SHELL_FILES:
        shutil.copy2(source / name, destination / name)


def main():
    sys.path.insert(0, str(ROOT))
    from backend.studio.bake_posters import BAKE_COMMAND, check_baked
    from backend.studio.peeks import check_baked as check_peeks
    from backend.studio.service import StudioService

    service = StudioService()
    stale = check_baked(service)
    if stale:
        raise RuntimeError(f"Missing or stale gallery posters: {', '.join(stale)}. Run {BAKE_COMMAND}")
    stale = check_peeks(service)
    if stale:
        raise RuntimeError(f"Missing, stale or oversized gallery peeks: {', '.join(stale)}. Run {BAKE_COMMAND}")
    destination = DESKTOP / "dist/ManimStudio"
    if not (RUNTIME / "ready.json").is_file() or not (DESKTOP / "build/frontend/index.html").is_file():
        raise RuntimeError("Run desktop/dev.ps1 -Smoke to prepare and validate the runtime/frontend first.")
    compiler = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        raise RuntimeError("The build host needs the .NET Framework C# compiler to produce the GUI starter.")
    remove_generated(destination)
    destination.mkdir(parents=True)
    shutil.copytree(RUNTIME, destination / "runtime", ignore=shutil.ignore_patterns("__pycache__", "ready.json"))
    shutil.copytree(ROOT / "backend", destination / "backend", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    shutil.copytree(DESKTOP / "build/frontend", destination / "frontend/dist")
    shell = destination / "shell"
    shell.mkdir()
    copy_shell(DESKTOP, shell)
    runtime_paths(destination / "runtime", destination / "backend", shell)
    snapshot = {p.relative_to(destination / "backend").as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((destination / "backend").rglob("*")) if p.is_file()}
    (destination / "backend-snapshot.sha256.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
                    "/r:System.Windows.Forms.dll", f"/out:{destination / 'Manim Studio.exe'}",
                    str(DESKTOP / "native/StudioHost.cs")], check=True)
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")
    shutil.copy2(DESKTOP / "README.md", destination / "DESKTOP-README.md")
    shutil.copy2(DESKTOP / "VALIDATION.md", destination / "VALIDATION.md")
    # Validate using the relocated runtime with a separate workspace, never developer data.
    subprocess.run([str(destination / "runtime/python.exe"), "-B", str(DESKTOP / "scripts/smoke.py"),
                    "--app-root", str(destination), "--data-dir", str(DESKTOP / "build/package-smoke")], check=True)
    # Other agents may be editing backend while packaging. Do not report a stale snapshot as current.
    for relative, digest in snapshot.items():
        source = ROOT / "backend" / relative
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Backend changed during packaging ({relative}); rerun package.ps1 for a current snapshot.")
    files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(destination.rglob("*")) if p.is_file()}
    (destination / "manifest.sha256.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    print(f"Unsigned portable directory validated: {destination}")
    print("No installer, signing or publishing was performed.")


if __name__ == "__main__":
    main()
