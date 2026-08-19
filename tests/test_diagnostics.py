import os
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from diagnostics import (  # noqa: E402
    generate_profile,
    get_cpu_info,
    get_gpu_info,
    get_ram_info,
    write_manim_config_file,
)


class DiagnosticsTests(unittest.TestCase):
    def test_get_cpu_info_returns_valid_dict(self):
        info = get_cpu_info()
        self.assertIn("model", info)
        self.assertIn("physical_cores", info)
        self.assertIn("logical_threads", info)
        self.assertGreaterEqual(info["physical_cores"], 1)
        self.assertGreaterEqual(info["logical_threads"], 1)

    def test_get_ram_info_returns_non_negative(self):
        ram = get_ram_info()
        self.assertIsInstance(ram, float)
        self.assertGreaterEqual(ram, 0.0)

    def test_get_gpu_info_returns_devices_and_cuda_flag(self):
        gpu = get_gpu_info()
        self.assertIn("devices", gpu)
        self.assertIn("has_cuda", gpu)
        self.assertIsInstance(gpu["devices"], list)
        self.assertGreater(len(gpu["devices"]), 0)

    def test_generate_profile_structure(self):
        profile = generate_profile()
        self.assertIn(profile["profile"], ("eco", "balanced", "workstation"))
        self.assertIn("preview_quality", profile)
        self.assertIn("default_fps", profile)
        self.assertIn("default_resolution", profile)
        self.assertGreaterEqual(profile["recommended_threads"], 1)

    def test_write_manim_config_file_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = generate_profile()
            res = write_manim_config_file(tmp, profile)
            self.assertTrue(res)
            cfg_path = os.path.join(tmp, "manim.cfg")
            self.assertTrue(os.path.exists(cfg_path))
            with open(cfg_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("[CLI]", content)
            self.assertIn("write_to_movie = True", content)

    def test_write_manim_config_file_with_incomplete_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = write_manim_config_file(tmp, {})
            self.assertTrue(res)
            cfg_path = os.path.join(tmp, "manim.cfg")
            self.assertTrue(os.path.exists(cfg_path))


if __name__ == "__main__":
    unittest.main()
