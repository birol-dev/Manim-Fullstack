"""Installer round-trip tests. Run on Windows with system Python: python -m unittest desktop.tests.test_installer -v.

The installer is built with a tiny fake payload and installed under a temporary folder. The /dir:
argument switches to the test uninstall key and skips shortcuts, so the real app is never touched.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP / "scripts"))
import build_installer

TEST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ManimStudio-Test"


def key_exists() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY):
            return True
    except FileNotFoundError:
        return False


def remove_test_key() -> None:
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    except FileNotFoundError:
        pass


def wait_until(predicate, timeout=60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


@unittest.skipUnless(sys.platform == "win32", "The installer is Windows-only")
@unittest.skipUnless(build_installer.compiler_path().is_file(),
                     "The .NET Framework C# compiler is not installed")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        remove_test_key()

    def tearDown(self):
        remove_test_key()

    def make_installer(self, folder: Path, marker: str = "first") -> Path:
        payload = folder / "payload"
        (payload / "runtime").mkdir(parents=True, exist_ok=True)
        (payload / "Manim Studio.exe").write_bytes(b"fake host " + marker.encode())
        (payload / "runtime" / "python.exe").write_bytes(b"fake python")
        # Random bytes do not compress, so Uninstall.exe is unmistakably a small fraction of Setup.
        (payload / "runtime" / "padding.bin").write_bytes(os.urandom(2 * 1024 * 1024))
        (payload / "LICENSE").write_text("MIT License", encoding="utf-8")
        installer = folder / "ManimStudioSetup.exe"
        build_installer.build(payload, installer, version="9.9.9", sign=False)
        with zipfile.ZipFile(io.BytesIO(build_installer.read_payload(installer))) as archive:
            self.assertIn("Manim Studio.exe", archive.namelist())
            self.assertIn("runtime/python.exe", archive.namelist())
        return installer

    def test_silent_install_upgrade_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="studio-installer-") as temporary:
            folder = Path(temporary)
            installer = self.make_installer(folder)
            target = folder / "installed"

            start_menu = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Manim Studio.lnk"
            desktop = Path(os.environ["USERPROFILE"]) / "Desktop/Manim Studio.lnk"
            shortcuts_before = (start_menu.exists(), desktop.exists())

            completed = subprocess.run([str(installer), "/S", "/nowebview2", "/dir:" + str(target)],
                                       capture_output=True, text=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((target / "Manim Studio.exe").read_bytes(), b"fake host first")
            self.assertTrue((target / "runtime/python.exe").is_file())
            self.assertTrue((target / "Uninstall.exe").is_file())
            self.assertEqual((start_menu.exists(), desktop.exists()), shortcuts_before)

            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY) as key:
                self.assertEqual(winreg.QueryValueEx(key, "DisplayName")[0], "Manim Studio")
                self.assertEqual(winreg.QueryValueEx(key, "DisplayVersion")[0], "9.9.9")
                self.assertEqual(Path(winreg.QueryValueEx(key, "InstallLocation")[0]), target)
                self.assertIn(str(target), winreg.QueryValueEx(key, "UninstallString")[0])
                self.assertIn(str(target), winreg.QueryValueEx(key, "DisplayIcon")[0])
                self.assertGreater(winreg.QueryValueEx(key, "EstimatedSize")[0], 0)
                self.assertEqual(winreg.QueryValueEx(key, "NoModify")[0], 1)
                self.assertEqual(winreg.QueryValueEx(key, "NoRepair")[0], 1)

            # A second install replaces the payload in place and keeps the folder usable.
            upgraded = self.make_installer(folder, marker="second")
            completed = subprocess.run([str(upgraded), "/S", "/nowebview2", "/dir:" + str(target)],
                                       capture_output=True, text=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((target / "Manim Studio.exe").read_bytes(), b"fake host second")

            # Uninstall.exe is only the setup stub: no payload and no 16-byte trailer.
            payload_size = len(build_installer.read_payload(upgraded))
            uninstall_size = (target / "Uninstall.exe").stat().st_size
            self.assertEqual(uninstall_size, upgraded.stat().st_size - payload_size - 16)
            self.assertLess(uninstall_size * 4, upgraded.stat().st_size)

            # Uninstall hands off to a temp copy, so the launcher returns before the folder is gone.
            completed = subprocess.run([str(target / "Uninstall.exe"), "/uninstall", "/S",
                                        "/dir:" + str(target)], capture_output=True, text=True, timeout=120)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(wait_until(lambda: not target.exists() and not key_exists()))

    def test_silent_uninstall_refuses_while_app_is_running(self):
        with tempfile.TemporaryDirectory(prefix="studio-installer-busy-") as temporary:
            folder = Path(temporary)
            payload = folder / "payload"
            (payload / "runtime").mkdir(parents=True)
            # A real executable named like the app, started from the install folder.
            shutil.copyfile(Path(os.environ["SystemRoot"]) / "System32" / "ping.exe",
                            payload / "Manim Studio.exe")
            (payload / "runtime" / "python.exe").write_bytes(b"fake python")
            installer = folder / "ManimStudioSetup.exe"
            build_installer.build(payload, installer, version="9.9.9", sign=False)
            target = folder / "installed"

            completed = subprocess.run([str(installer), "/S", "/nowebview2", "/dir:" + str(target)],
                                       capture_output=True, text=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(key_exists())

            running = subprocess.Popen([str(target / "Manim Studio.exe"), "-t", "127.0.0.1"],
                                       cwd=str(target), stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
            try:
                self.assertIsNone(running.poll())
                # The installed launcher hands off to a temp copy and returns 0, so run the stub the
                # way the handoff does to observe the refusal code itself.
                completed = subprocess.run([str(target / "Uninstall.exe"), "/uninstall", "/fromtemp", "/S",
                                            "/dir:" + str(target)], capture_output=True, text=True, timeout=120)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertTrue((target / "Manim Studio.exe").is_file())
                self.assertTrue((target / "runtime" / "python.exe").is_file())
                self.assertTrue((target / "Uninstall.exe").is_file())
                self.assertTrue(key_exists())
            finally:
                running.kill()
                running.wait(timeout=30)

    def test_zip_slip_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="studio-installer-slip-") as temporary:
            folder = Path(temporary)
            payload = folder / "payload.zip"
            with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("../escaped.txt", "should not be written")
                archive.writestr("Manim Studio.exe", b"fake host")
            installer = folder / "ManimStudioSetup.exe"
            build_installer.build_from_zip(payload, installer, version="9.9.9", sign=False)
            target = folder / "installed"

            completed = subprocess.run([str(installer), "/S", "/nowebview2", "/dir:" + str(target)],
                                       capture_output=True, text=True, timeout=120)
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse((folder / "escaped.txt").exists())
            self.assertFalse(target.exists())
            self.assertFalse(key_exists())


if __name__ == "__main__":
    unittest.main()
