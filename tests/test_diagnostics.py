import os
from unittest.mock import MagicMock, mock_open, patch
import pytest

from diagnostics import (
    generate_profile,
    get_binary_paths,
    get_cpu_info,
    get_gpu_info,
    get_ram_info,
    write_manim_config_file,
)


def test_get_cpu_info_returns_valid_dict():
    info = get_cpu_info()
    assert "model" in info
    assert "physical_cores" in info
    assert "logical_threads" in info
    assert info["physical_cores"] >= 1
    assert info["logical_threads"] >= 1


def test_get_cpu_info_windows_powershell_success():
    with patch("platform.system", return_value="Windows"):
        with patch("subprocess.check_output", return_value=b"Intel Core i9-13900K\r\n"):
            info = get_cpu_info()
            assert info["model"] == "Intel Core i9-13900K"


def test_get_cpu_info_windows_wmic_fallback():
    def mock_check_output(cmd, **kwargs):
        if "powershell" in cmd:
            raise RuntimeError("PowerShell disabled")
        if "wmic" in cmd[0]:
            return b"Name\r\nAMD Ryzen 9 5950X\r\n"
        raise RuntimeError("Unknown cmd")

    with patch("platform.system", return_value="Windows"):
        with patch("os.path.exists", return_value=True):
            with patch("subprocess.check_output", side_effect=mock_check_output):
                info = get_cpu_info()
                assert info["model"] == "AMD Ryzen 9 5950X"


def test_get_cpu_info_windows_all_fail():
    with patch("platform.system", return_value="Windows"):
        with patch("subprocess.check_output", side_effect=Exception("Failed")):
            with patch("os.path.exists", return_value=False):
                info = get_cpu_info()
                assert info["model"] == "Unknown Processor"


def test_get_cpu_info_darwin_sysctl():
    with patch("platform.system", return_value="Darwin"):
        with patch("subprocess.check_output", return_value=b"Apple M2 Max\n"):
            info = get_cpu_info()
            assert info["model"] == "Apple M2 Max"


def test_get_cpu_info_darwin_fallback():
    with patch("platform.system", return_value="Darwin"):
        with patch("subprocess.check_output", side_effect=Exception("No sysctl")):
            with patch("platform.processor", return_value=""):
                info = get_cpu_info()
                assert info["model"] == "Apple Silicon / Intel Mac"


def test_get_cpu_info_linux_proc_cpuinfo():
    cpuinfo_data = "processor : 0\nmodel name : AMD EPYC 7763\ncores : 64\n"
    with patch("platform.system", return_value="Linux"):
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=cpuinfo_data)):
                info = get_cpu_info()
                assert info["model"] == "AMD EPYC 7763"


def test_get_cpu_info_linux_fallback():
    with patch("platform.system", return_value="Linux"):
        with patch("os.path.exists", side_effect=Exception("Disk error")):
            with patch("platform.processor", return_value="Linux ARM64"):
                info = get_cpu_info()
                assert info["model"] == "Linux ARM64"


def test_get_cpu_info_other_os():
    with patch("platform.system", return_value="FreeBSD"):
        with patch("platform.processor", return_value="BSD Generic"):
            info = get_cpu_info()
            assert info["model"] == "BSD Generic"


def test_get_ram_info_success_and_exception():
    ram = get_ram_info()
    assert isinstance(ram, float)
    assert ram >= 0.0

    with patch("psutil.virtual_memory", side_effect=Exception("RAM error")):
        assert get_ram_info() == 0.0


def test_get_gpu_info_nvidia_smi_success():
    csv_output = b"NVIDIA GeForce RTX 4090, 24576 MiB\n"
    with patch("subprocess.check_output", return_value=csv_output):
        gpu = get_gpu_info()
        assert gpu["has_cuda"] is True
        assert len(gpu["devices"]) == 1
        assert gpu["devices"][0]["name"] == "NVIDIA GeForce RTX 4090"
        assert gpu["devices"][0]["type"] == "NVIDIA"
        assert gpu["devices"][0]["vram"] == "24576 MiB"


def test_get_gpu_info_windows_powershell_success():
    with patch("subprocess.check_output", side_effect=[Exception("No nvidia-smi"), b"Intel(R) UHD Graphics 770\r\n"]):
        with patch("platform.system", return_value="Windows"):
            gpu = get_gpu_info()
            assert gpu["has_cuda"] is False
            assert len(gpu["devices"]) == 1
            assert "Intel(R) UHD Graphics" in gpu["devices"][0]["name"]


def test_get_gpu_info_windows_wmic_fallback():
    def mock_check_output(cmd, **kwargs):
        if "nvidia-smi" in cmd[0]:
            raise RuntimeError("No nvidia")
        if "powershell" in cmd[0]:
            raise RuntimeError("No powershell")
        if "wmic" in cmd[0]:
            return b"Name\r\nIntel Iris Xe Graphics\r\n"
        raise RuntimeError("Unknown cmd")

    with patch("platform.system", return_value="Windows"):
        with patch("os.path.exists", return_value=True):
            with patch("subprocess.check_output", side_effect=mock_check_output):
                gpu = get_gpu_info()
                assert len(gpu["devices"]) == 1
                assert gpu["devices"][0]["name"] == "Intel Iris Xe Graphics"


def test_get_gpu_info_fallback_software_renderer():
    with patch("subprocess.check_output", side_effect=Exception("No GPU tool")):
        gpu = get_gpu_info()
        assert len(gpu["devices"]) == 1
        assert gpu["devices"][0]["type"] == "Software"
        assert gpu["has_cuda"] is False


def test_get_binary_paths_discovery():
    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda cmd: f"/usr/local/bin/{cmd}" if cmd in ("manim", "ffmpeg", "latex", "dvisvgm") else None
        binaries = get_binary_paths()
        assert binaries["manim"] == "/usr/local/bin/manim"
        assert binaries["ffmpeg"] == "/usr/local/bin/ffmpeg"
        assert binaries["latex"] == "/usr/local/bin/latex"
        assert binaries["latex_available"] is True


def test_get_binary_paths_fallback_scanning(tmp_path):
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("", encoding="utf-8")
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "manim.exe").write_text("", encoding="utf-8")
    (scripts / "ffmpeg.exe").write_text("", encoding="utf-8")

    with patch("shutil.which", return_value=None):
        with patch("sys.executable", str(fake_py)):
            binaries = get_binary_paths()
            assert binaries["manim"] == str(scripts / "manim.exe")
            assert binaries["ffmpeg"] == str(scripts / "ffmpeg.exe")


def test_get_binary_paths_none_found():
    with patch("shutil.which", return_value=None):
        with patch("sys.executable", None):
            with patch("os.path.exists", return_value=False):
                binaries = get_binary_paths()
                assert binaries["manim"] == "Not Found"
                assert binaries["ffmpeg"] == "Not Found"
                assert binaries["latex"] == "Not Found"
                assert binaries["latex_available"] is False


@pytest.mark.parametrize(
    "ram,cores,cuda,expected_profile",
    [
        (64.0, 16, True, "workstation"),
        (16.0, 8, False, "balanced"),
        (4.0, 2, False, "eco"),
    ],
)
def test_generate_profile_tiers(ram, cores, cuda, expected_profile):
    mock_cpu = {"model": "Test CPU", "physical_cores": cores, "logical_threads": cores}
    mock_gpu = {"devices": [{"name": "GPU", "type": "NVIDIA" if cuda else "Intel"}], "has_cuda": cuda}
    with patch("diagnostics.get_cpu_info", return_value=mock_cpu):
        with patch("diagnostics.get_ram_info", return_value=ram):
            with patch("diagnostics.get_gpu_info", return_value=mock_gpu):
                profile = generate_profile()
                assert profile["profile"] == expected_profile
                assert profile["recommended_threads"] >= 1
                assert "preview_quality" in profile
                assert "default_fps" in profile


def test_generate_profile_cloud_docker_detection():
    with patch.dict(os.environ, {"RENDER": "true"}):
        profile = generate_profile()
        assert profile["profile"] == "eco"
        assert profile["recommended_threads"] == 1


def test_write_manim_config_file(tmp_path):
    profile = {
        "profile": "balanced",
        "default_fps": 30,
        "default_resolution": "1280x720",
        "hardware": {"cpu": {"model": "Core i7"}},
    }
    assert write_manim_config_file(str(tmp_path), profile) is True
    target = tmp_path / "manim.cfg"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "frame_rate = 30" in content
    assert "pixel_width = 1280" in content
    assert "pixel_height = 720" in content

    with patch("builtins.open", side_effect=OSError("Disk error")):
        assert write_manim_config_file(str(tmp_path), profile) is False
