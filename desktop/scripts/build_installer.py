"""Build desktop/dist/ManimStudioSetup.exe from the packaged portable folder.

The setup executable is the C# 5 WinForms stub from native/Setup.cs with a deflated
zip of dist/ManimStudio appended to it:

    [stub exe][zip payload][8-byte little-endian payload length][8-byte magic]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile

DESKTOP = Path(__file__).resolve().parents[1]
ROOT = DESKTOP.parent
PAYLOAD_DIR = DESKTOP / "dist/ManimStudio"
OUTPUT = DESKTOP / "dist/ManimStudioSetup.exe"
BUILD = DESKTOP / "build/installer"
MAGIC = b"MSETUP01"
VERSION_PLACEHOLDER = "@@VERSION@@"

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <assemblyIdentity version="1.0.0.0" name="ManimStudioSetup.app" />
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v2">
    <security>
      <requestedPrivileges xmlns="urn:schemas-microsoft-com:asm.v3">
        <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" />
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
    </windowsSettings>
  </application>
</assembly>
"""


def project_version() -> str:
    """The one app version, read from backend/studio/version.py."""
    source = (ROOT / "backend/studio/version.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', source, re.MULTILINE)
    if match is None:
        raise RuntimeError("backend/studio/version.py has no APP_VERSION.")
    return match.group(1)


def compiler_path() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"


def find_existing_icon() -> Path | None:
    """Use an icon already in the repository instead of drawing one."""
    for folder in (DESKTOP / "native", DESKTOP / "assets", ROOT / "frontend/public", ROOT / "docs", ROOT / "website"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.ico")):
            return path
    return None


def ensure_icon(destination: Path | None = None) -> Path:
    """Return an .ico for the app and setup exe, generating a simple mark with Pillow."""
    existing = find_existing_icon()
    if existing is not None:
        return existing
    target = destination or (DESKTOP / "build/ManimStudio.ico")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise RuntimeError(
            "No .ico exists in the repository and Pillow is needed to draw one. "
            "Install it with: python -m pip install pillow"
        ) from error
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, size - 8, size - 8), radius=52, fill=(0, 0, 0, 255))
    draw.polygon([(100, 76), (100, 180), (184, 128)], fill=(255, 255, 255, 255))
    image.save(target, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return target


def sign_file(path: Path) -> None:
    """Run an optional signing command; MANIM_SIGN_CMD may use {file} or get the path appended."""
    template = os.environ.get("MANIM_SIGN_CMD", "").strip()
    if not template:
        print(f"MANIM_SIGN_CMD is not set; leaving {path.name} unsigned.")
        return
    quoted = f'"{path}"'
    command = template.replace("{file}", quoted) if "{file}" in template else f"{template} {quoted}"
    print(f"Signing {path.name}...", flush=True)
    completed = subprocess.run(command, shell=True)
    if completed.returncode:
        raise RuntimeError(f"Signing failed for {path.name} (exit code {completed.returncode}).")


def make_payload_zip(payload_dir: Path, destination: Path) -> Path:
    if not payload_dir.is_dir():
        raise RuntimeError(f"Missing packaged folder: {payload_dir}. Run desktop/package.ps1 first.")
    if not (payload_dir / "Manim Studio.exe").is_file():
        raise RuntimeError(f"{payload_dir} does not contain Manim Studio.exe. Run desktop/package.ps1 first.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(payload_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(payload_dir).as_posix())
    return destination


def compile_stub(source: Path, output: Path, icon: Path, manifest: Path,
                 compiler: Path | None = None) -> Path:
    compiler = compiler or compiler_path()
    if not compiler.is_file():
        raise RuntimeError("The build host needs the .NET Framework C# compiler (csc.exe) for Setup.exe.")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
                    "/r:System.Drawing.dll", "/r:System.Windows.Forms.dll", "/r:System.IO.Compression.dll",
                    f"/win32icon:{icon}", f"/win32manifest:{manifest}", f"/out:{output}", str(source)],
                   check=True)
    return output


def append_payload(stub: Path, payload_zip: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as target:
        with open(stub, "rb") as source:
            shutil.copyfileobj(source, target)
        with open(payload_zip, "rb") as source:
            shutil.copyfileobj(source, target)
        target.write(struct.pack("<Q", payload_zip.stat().st_size))
        target.write(MAGIC)
    return output


def read_payload(installer: Path) -> bytes:
    """Read the appended zip back; useful for tests and diagnostics."""
    data = installer.read_bytes()
    index = data.rfind(MAGIC)
    if index < 8:
        raise ValueError("No installer payload trailer found.")
    size = struct.unpack("<Q", data[index - 8:index])[0]
    start = index - 8 - size
    if start < 0:
        raise ValueError("Installer payload is truncated.")
    return data[start:index - 8]


def stamped_source(version: str) -> Path:
    source = (DESKTOP / "native/Setup.cs").read_text(encoding="utf-8")
    if VERSION_PLACEHOLDER not in source:
        raise RuntimeError("native/Setup.cs no longer contains the version placeholder.")
    BUILD.mkdir(parents=True, exist_ok=True)
    destination = BUILD / "Setup.stamped.cs"
    destination.write_text(source.replace(VERSION_PLACEHOLDER, version), encoding="utf-8")
    return destination


def build_from_zip(payload_zip: Path, output: Path = OUTPUT, version: str | None = None,
                   sign: bool = True) -> Path:
    version = version or project_version()
    icon = ensure_icon()
    manifest = BUILD / "ManimStudioSetup.manifest"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(MANIFEST, encoding="utf-8")
    stub = BUILD / "ManimStudioSetup.stub.exe"
    compile_stub(stamped_source(version), stub, icon, manifest)
    append_payload(stub, payload_zip, output)
    if sign:
        sign_file(output)
    return output


def build(payload_dir: Path = PAYLOAD_DIR, output: Path = OUTPUT, version: str | None = None,
          sign: bool = True) -> Path:
    payload_zip = BUILD / "ManimStudio.payload.zip"
    make_payload_zip(payload_dir, payload_zip)
    return build_from_zip(payload_zip, output, version, sign)


def main():
    parser = argparse.ArgumentParser(description="Build ManimStudioSetup.exe from desktop/dist/ManimStudio.")
    parser.add_argument("--payload", type=Path, default=PAYLOAD_DIR, help="Packaged app folder to include.")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Where to write the setup executable.")
    parser.add_argument("--version", default=None, help="DisplayVersion; defaults to backend/studio/version.py.")
    parser.add_argument("--no-sign", action="store_true", help="Skip MANIM_SIGN_CMD even when it is set.")
    args = parser.parse_args()
    result = build(args.payload, args.output, args.version, sign=not args.no_sign)
    print(f"Installer written: {result} ({result.stat().st_size / (1024 * 1024):.1f} MB)")


if __name__ == "__main__":
    main()
