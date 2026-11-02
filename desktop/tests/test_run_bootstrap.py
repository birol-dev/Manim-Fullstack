"""Pure helper tests for run.py's first-run setup. No pip install and no network are used."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run


class VersionTests(unittest.TestCase):
    def test_python_311_and_newer_are_supported(self):
        self.assertTrue(run.python_version_supported((3, 11)))
        self.assertTrue(run.python_version_supported((3, 12, 8)))
        self.assertTrue(run.python_version_supported((4, 0)))

    def test_python_310_is_refused(self):
        self.assertFalse(run.python_version_supported((3, 10, 14)))
        self.assertFalse(run.python_version_supported((2, 7)))


class StampTests(unittest.TestCase):
    def test_requirements_digest_tracks_content(self):
        with tempfile.TemporaryDirectory(prefix="studio-run-") as temporary:
            requirements = Path(temporary) / "requirements.txt"
            requirements.write_text("fastapi\nuvicorn\n", encoding="utf-8")
            first = run.requirements_digest(str(requirements))
            self.assertEqual(first, run.requirements_digest(str(requirements)))
            requirements.write_text("fastapi\nuvicorn\nmanim\n", encoding="utf-8")
            self.assertNotEqual(first, run.requirements_digest(str(requirements)))

    def test_stamp_round_trip_and_changed_hash(self):
        with tempfile.TemporaryDirectory(prefix="studio-run-") as temporary:
            stamp = Path(temporary) / "manim-requirements.sha256"
            self.assertFalse(run.stamp_is_current(str(stamp), "abc"))
            run.write_stamp(str(stamp), "abc")
            self.assertTrue(run.stamp_is_current(str(stamp), "abc"))
            self.assertFalse(run.stamp_is_current(str(stamp), "def"))


class VirtualenvTests(unittest.TestCase):
    def test_prefix_comparison(self):
        self.assertFalse(run.inside_virtualenv(r"C:\Python312", r"C:\Python312"))
        self.assertTrue(run.inside_virtualenv("/home/me/project/.venv", "/usr"))


class PackageManagerTests(unittest.TestCase):
    def test_linux_package_manager_choice(self):
        self.assertIn("apt install", run.system_install_command("linux", {"apt-get", "dnf"}))
        self.assertIn("dnf install", run.system_install_command("linux", {"dnf"}))
        self.assertIn("pacman", run.system_install_command("linux", {"pacman"}))
        self.assertIsNone(run.system_install_command("linux", set()))

    def test_macos_uses_homebrew(self):
        self.assertIn("brew install", run.system_install_command("darwin", {"brew"}))
        self.assertIsNone(run.system_install_command("darwin", set()))

    def test_windows_needs_no_system_command(self):
        self.assertIsNone(run.system_install_command("win32", {"apt-get"}))

    def test_linux_library_probe(self):
        missing = lambda name: None
        self.assertFalse(run.linux_libraries_present(which=missing))
        found = lambda name: "/usr/bin/" + name
        ok = lambda *args, **kwargs: types.SimpleNamespace(returncode=0)
        broken = lambda *args, **kwargs: types.SimpleNamespace(returncode=1)
        self.assertTrue(run.linux_libraries_present(which=found, runner=ok))
        self.assertFalse(run.linux_libraries_present(which=found, runner=broken))

    def test_macos_library_probe(self):
        missing = lambda name: None
        self.assertFalse(run.macos_libraries_present(which=missing))


class DependencyTests(unittest.TestCase):
    def test_importable_and_missing_packages(self):
        self.assertEqual(run.missing_packages(("sys",)), [])
        self.assertEqual(run.missing_packages(("definitely_not_a_real_module_xyz",)),
                         ["definitely_not_a_real_module_xyz"])

    def test_plain_diagnosis_for_common_failures(self):
        self.assertIn("internet", run.diagnose_pip_failure("Could not find a version that satisfies"))
        self.assertIn("system library", run.diagnose_pip_failure("pkg-config: command not found"))
        self.assertIn("Pip is missing", run.diagnose_pip_failure("No module named pip"))
        self.assertIn("failed", run.diagnose_pip_failure("something unexpected"))


if __name__ == "__main__":
    unittest.main()
