"""Build-host only: prepare app-local CPython, wheels, and a separate static UI build."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile

DESKTOP = Path(__file__).resolve().parents[1]
ROOT = DESKTOP.parent
RUNTIME = DESKTOP / ".runtime"
CACHE = DESKTOP / ".cache"


def remove_generated(path: Path):
    resolved = path.resolve()
    if not resolved.is_relative_to(DESKTOP.resolve()) or resolved == DESKTOP.resolve():
        raise RuntimeError(f"Refusing to remove a path outside desktop: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def runtime_paths(runtime: Path, backend: Path, shell: Path):
    import os
    # ._pth applies even to -m studio.worker / -m manim grandchildren. No registry/user packages.
    (runtime / "python312._pth").write_text("\n".join(("python312.zip", ".", "Lib/site-packages",
        "Lib/site-packages/win32", "Lib/site-packages/win32/lib", "Lib/site-packages/pythonwin",
        os.path.relpath(backend, runtime), os.path.relpath(shell, runtime), "")), encoding="utf-8")


def prepare_runtime(refresh: bool):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Build preparation needs 64-bit Windows Python 3.12 with pip (build host only).")
    spec = json.loads((DESKTOP / "runtime.json").read_text())
    RUNTIME.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    archive = CACHE / "python-embed-amd64.zip"
    if not archive.exists():
        print("Downloading app-local CPython from python.org...", flush=True)
        urllib.request.urlretrieve(spec["url"], archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != spec["sha256"]:
        raise RuntimeError(f"Embedded Python SHA-256 mismatch. Remove {archive} and retry.")
    if not (RUNTIME / "python.exe").exists():
        with zipfile.ZipFile(archive) as z:
            z.extractall(RUNTIME)
    runtime_paths(RUNTIME, ROOT / "backend", DESKTOP)
    requirements = [ROOT / "backend/requirements.txt", DESKTOP / "requirements.txt"]
    constraints = DESKTOP / "constraints.txt"
    inputs = b"".join(p.read_bytes() for p in requirements) + (constraints.read_bytes() if constraints.exists() else b"")
    fingerprint = hashlib.sha256(inputs + (DESKTOP / "runtime.json").read_bytes()).hexdigest()
    marker = RUNTIME / "ready.json"
    current = json.loads(marker.read_text()) if marker.exists() else {}
    if refresh or current.get("fingerprint") != fingerprint:
        marker.unlink(missing_ok=True)
        target = RUNTIME / "Lib/site-packages"
        remove_generated(target)
        target.mkdir(parents=True)
        command = [sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check", "install",
                   "--no-user", "--no-compile", "--cache-dir", str(CACHE / "pip"), "--target", str(target),
                   # Pure Python sdists are fine. Native dependencies must have Windows wheels.
                   "--only-binary=manim,manimpango,pycairo,numpy,scipy,av,pillow,pythonnet,moderngl,glcontext,skia-pathops,mapbox-earcut"]
        for req in requirements:
            command.extend(["-r", str(req)])
        if constraints.exists():
            command.extend(["-c", str(constraints)])
        subprocess.run(command, check=True, cwd=DESKTOP)
        # With site disabled, pywin32's .pth hook is not executed. Its extension
        # dependencies belong beside python.exe so every isolated subprocess can load them.
        for dll in (target / "pywin32_system32").glob("*.dll"):
            shutil.copy2(dll, RUNTIME / dll.name)
        subprocess.run([str(RUNTIME / "python.exe"), "-c",
                        "import manim,webview,uvicorn,fastapi,win32api; from webview.platforms import edgechromium; print('Embedded native imports OK')"], check=True)
        subprocess.run([str(RUNTIME / "python.exe"), "-c",
                       "import importlib.metadata as m,pathlib; pathlib.Path(r'" + str(RUNTIME / "requirements-resolved.txt") +
                       "').write_text(''.join(sorted(d.metadata['Name']+'=='+d.version+'\\n' for d in m.distributions(path=[r'" + str(target) + "']))))"], check=True)
        marker.write_text(json.dumps({"fingerprint": fingerprint, "python": spec["version"]}, indent=2))


def build_frontend():
    import os
    npm = shutil.which("npm.cmd")
    if not npm or not (ROOT / "frontend/node_modules/vite/bin/vite.js").exists():
        raise RuntimeError("Build host needs Node/npm and the existing frontend dependencies. No packages were installed globally.")
    env = dict(os.environ, VITE_BACKEND_URL="")
    output = DESKTOP / "build/frontend"
    remove_generated(output)
    subprocess.run([npm, "exec", "--", "vite", "build", "--outDir", str(output), "--base", "/"],
                   cwd=ROOT / "frontend", env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--refresh-deps", action="store_true")
    args = parser.parse_args()
    prepare_runtime(args.refresh_deps)
    if not args.skip_frontend:
        build_frontend()


if __name__ == "__main__":
    main()
