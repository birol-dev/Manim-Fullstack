import os
import shutil
import platform
import subprocess
import sys
import time
import functools
import psutil

# Cached hardware / binary detection
_PROFILE_CACHE = None
_PROFILE_CACHE_TIME = 0.0
_BINARY_PATHS_CACHE = None
_BINARY_PATHS_CACHE_TIME = 0.0
_CACHE_TTL_SECONDS = 300.0  # 5 minutes cache for system hardware profile

def _get_cpu_from_registry():
    """Fast registry lookup for CPU name on Windows (< 0.05ms)."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    return None

def get_cpu_info():
    """Returns CPU model, physical cores, and logical threads."""
    cpu_model = "Unknown Processor"
    try:
        # On Windows, first try instant registry lookup (< 0.05 ms) before spawning slow subprocesses
        if platform.system() == "Windows":
            reg_model = _get_cpu_from_registry()
            if reg_model:
                cpu_model = reg_model
            else:
                try:
                    # Try PowerShell first with timeout
                    out = subprocess.check_output(
                        ["powershell", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                        timeout=4,
                    ).decode("utf-8", errors="replace").strip()
                    if out:
                        cpu_model = out
                except Exception:
                    # Fallback to direct path of wmic
                    try:
                        wmic_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "wbem", "wmic.exe")
                        if os.path.exists(wmic_path):
                            out = subprocess.check_output(
                                [wmic_path, "cpu", "get", "name"],
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                                timeout=4,
                            ).decode("utf-8", errors="replace").strip()
                            lines = [line.strip() for line in out.split("\n") if line.strip()]
                            if len(lines) > 1:
                                cpu_model = lines[1]
                    except Exception:
                        pass
        elif platform.system() == "Darwin":
            try:
                out = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=2).decode("utf-8", errors="replace").strip()
                if out:
                    cpu_model = out
            except Exception:
                cpu_model = platform.processor() or "Apple Silicon / Intel Mac"
        elif platform.system() == "Linux":
            try:
                if os.path.exists("/proc/cpuinfo"):
                    with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if "model name" in line:
                                cpu_model = line.split(":", 1)[1].strip()
                                break
            except Exception:
                cpu_model = platform.processor() or "Linux Processor"
        elif platform.system() != "Windows":
            cpu_model = platform.processor() or "Unknown CPU"
    except Exception:
        cpu_model = platform.processor() or "Unknown CPU"

    physical = psutil.cpu_count(logical=False) or 1
    logical = psutil.cpu_count(logical=True) or 1
    return {
        "model": cpu_model,
        "physical_cores": max(1, physical),
        "logical_threads": max(1, logical),
    }

def get_ram_info():
    """Returns total RAM in GB."""
    try:
        total_bytes = psutil.virtual_memory().total
        total_gb = round(total_bytes / (1024 ** 3), 2)
        return total_gb
    except Exception:
        return 0.0

def get_gpu_info():
    """Detects graphics hardware, VRAM if possible, and CUDA support."""
    gpus = []
    has_cuda = False
    
    # 1. Try to run nvidia-smi to detect NVIDIA GPUs and CUDA
    try:
        kwargs = {}
        if platform.system() == "Windows" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            timeout=4,
            **kwargs,
        ).decode("utf-8", errors="replace")
        for line in out.strip().split("\n"):
            if "," in line:
                name, mem = line.split(",")
                gpus.append({"name": name.strip(), "vram": mem.strip(), "type": "NVIDIA"})
                has_cuda = True
    except Exception:
        pass

    # 2. If no NVIDIA found, check via PowerShell or WMIC
    if not gpus:
        try:
            if platform.system() == "Windows":
                # Try PowerShell CimInstance
                try:
                    out = subprocess.check_output(
                        ["powershell", "-Command", "(Get-CimInstance Win32_VideoController).Name"],
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                        timeout=4,
                    ).decode("utf-8", errors="replace").strip()
                    for line in out.split("\n"):
                        name = line.strip()
                        if name and "Virtual" not in name and "Mirror" not in name:
                            gpus.append({"name": name, "vram": "Unknown", "type": "Generic"})
                except Exception:
                    # Fallback to wmic with absolute path
                    wmic_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "wbem", "wmic.exe")
                    if os.path.exists(wmic_path):
                        out = subprocess.check_output(
                            [wmic_path, "path", "win32_VideoController", "get", "name"],
                            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                            timeout=4,
                        ).decode("utf-8", errors="replace").strip()
                        lines = [line.strip() for line in out.split("\n") if line.strip()]
                        for line in lines[1:]:
                            if line and "Virtual" not in line and "Mirror" not in line:
                                gpus.append({"name": line.strip(), "vram": "Unknown", "type": "Generic"})
        except Exception:
            pass

    return {
        "devices": gpus if gpus else [{"name": "Integrated Graphics / Software Renderer", "vram": "N/A", "type": "Software"}],
        "has_cuda": has_cuda
    }

def get_binary_paths(force_refresh: bool = False):
    """Locates manim, ffmpeg, latex, and dvisvgm paths."""
    global _BINARY_PATHS_CACHE, _BINARY_PATHS_CACHE_TIME
    manim_path = shutil.which("manim")
    ffmpeg_path = shutil.which("ffmpeg")
    latex_path = shutil.which("latex")
    dvisvgm_path = shutil.which("dvisvgm")

    # Double check Python environment and common paths if not in system PATH
    py_dir = os.path.dirname(sys.executable) if sys.executable else ""
    if py_dir:
        candidates_manim = [
            os.path.join(py_dir, "Scripts", "manim.exe"),
            os.path.join(py_dir, "manim.exe"),
            os.path.join(py_dir, "Scripts", "manim"),
            os.path.join(py_dir, "manim"),
            r"C:\tools\Manim\Scripts\manim.exe",
        ]
        if not manim_path:
            for cand in candidates_manim:
                if os.path.exists(cand):
                    manim_path = cand
                    break

        candidates_ffmpeg = [
            os.path.join(py_dir, "Scripts", "ffmpeg.exe"),
            os.path.join(py_dir, "ffmpeg.exe"),
            os.path.join(py_dir, "Scripts", "ffmpeg"),
            os.path.join(py_dir, "ffmpeg"),
        ]
        if not ffmpeg_path:
            for cand in candidates_ffmpeg:
                if os.path.exists(cand):
                    ffmpeg_path = cand
                    break

    if platform.system() == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        appdata = os.environ.get("APPDATA", "")
        
        miktex_user_bin = os.path.join(local_appdata, "Programs", "MiKTeX", "miktex", "bin", "x64")
        miktex_system_bin = os.path.join(program_files, "MiKTeX", "miktex", "bin", "x64")
        tinytex_win = os.path.join(appdata, "TinyTeX", "bin", "windows")
        tinytex_win32 = os.path.join(appdata, "TinyTeX", "bin", "win32")
        
        for bin_dir in [miktex_user_bin, miktex_system_bin, tinytex_win, tinytex_win32]:
            if os.path.exists(bin_dir):
                if not latex_path:
                    cand_latex = os.path.join(bin_dir, "latex.exe")
                    if os.path.exists(cand_latex):
                        latex_path = cand_latex
                if not dvisvgm_path:
                    cand_dvisvgm = os.path.join(bin_dir, "dvisvgm.exe")
                    if os.path.exists(cand_dvisvgm):
                        dvisvgm_path = cand_dvisvgm

    result = {
        "manim": manim_path or "Not Found",
        "ffmpeg": ffmpeg_path or "Not Found",
        "latex": latex_path or "Not Found",
        "dvisvgm": dvisvgm_path or "Not Found",
        "latex_available": latex_path is not None and dvisvgm_path is not None
    }
    _BINARY_PATHS_CACHE = result
    _BINARY_PATHS_CACHE_TIME = time.time()
    return result

def get_cached_binary_paths(force_refresh: bool = False) -> dict:
    """Returns cached binary paths when valid, otherwise refreshes."""
    global _BINARY_PATHS_CACHE, _BINARY_PATHS_CACHE_TIME
    now = time.time()
    if not force_refresh and _BINARY_PATHS_CACHE is not None and (now - _BINARY_PATHS_CACHE_TIME < _CACHE_TTL_SECONDS):
        return dict(_BINARY_PATHS_CACHE)
    return get_binary_paths(force_refresh=True)

def generate_profile():
    """Generates a hardware-specific configuration profile for Manim rendering."""
    cpu = get_cpu_info()
    ram = get_ram_info()
    gpu = get_gpu_info()
    binaries = get_binary_paths()

    # Detect if we are running on Render or inside a Docker container
    is_cloud = os.environ.get("RENDER") == "true" or os.environ.get("RUNNING_IN_DOCKER") == "true"

    threads = cpu["logical_threads"]
    
    # Profile decision logic
    if is_cloud:
        profile_name = "eco"
        preview_quality = "480p15"
        default_fps = 15
        default_res = "854x480"
        recommended_threads = 1
        description = "Optimized for resource-constrained cloud containers or Docker deployments. Threads and quality are limited to prevent out-of-memory (OOM) crashes."
    elif threads < 4 or ram < 6:
        profile_name = "eco"
        preview_quality = "480p15"
        default_fps = 15
        default_res = "854x480"
        recommended_threads = 1
        description = "Optimized for battery saving / lower-spec computers. Caching is aggressive and quality defaults are low for fast rendering."
    elif threads <= 8 and ram <= 16:
        profile_name = "balanced"
        preview_quality = "720p30"
        default_fps = 30
        default_res = "1280x720"
        recommended_threads = max(1, threads - 1)
        description = "Standard system configuration. Balanced preview quality and rendering speeds."
    else:
        profile_name = "workstation"
        preview_quality = "1080p60"
        default_fps = 60
        default_res = "1920x1080"
        recommended_threads = max(1, threads - 1)
        description = "High performance workstation. Previews are crisp and render settings use multithreaded FFMPEG encoders."

    # Can we use OpenGL hardware acceleration?
    opengl_capable = len(gpu["devices"]) > 0 and gpu["devices"][0]["type"] != "Software" and not is_cloud

    config = {
        "profile": profile_name,
        "description": description,
        "preview_quality": preview_quality,
        "default_fps": default_fps,
        "default_resolution": default_res,
        "recommended_threads": recommended_threads,
        "opengl_supported": opengl_capable,
        "hardware": {
            "cpu": cpu,
            "ram_gb": ram,
            "gpu": gpu
        },
        "dependencies": binaries
    }
    return config

def get_cached_profile(force_refresh: bool = False) -> dict:
    """Returns cached hardware profile if within TTL, else regenerates."""
    global _PROFILE_CACHE, _PROFILE_CACHE_TIME
    now = time.time()
    if not force_refresh and _PROFILE_CACHE is not None and (now - _PROFILE_CACHE_TIME < _CACHE_TTL_SECONDS):
        return dict(_PROFILE_CACHE)
    config = generate_profile()
    _PROFILE_CACHE = config
    _PROFILE_CACHE_TIME = now
    return dict(config)

def write_manim_config_file(workspace_path: str, profile_config: dict):
    """Generates a customized manim.cfg file inside the user's workspace to apply default speedups."""
    cfg_path = os.path.join(workspace_path, "manim.cfg")
    
    quality_profile = profile_config.get("profile", "balanced")
    cpu_model = profile_config.get("hardware", {}).get("cpu", {}).get("model", "Default CPU")
    fps = profile_config.get("default_fps", 30)
    res_parts = str(profile_config.get("default_resolution", "1280x720")).split("x")
    pixel_width = res_parts[0] if len(res_parts) == 2 else "1280"
    pixel_height = res_parts[1] if len(res_parts) == 2 else "720"
    
    cfg_content = f"""[CLI]
# Custom generated config optimized for your PC config: {cpu_model}
# Profile: {quality_profile}

# Logging configuration
write_to_movie = True
media_dir = ./media
log_dir = ./logs

# Frame parameters for defaults
frame_rate = {fps}
pixel_width = {pixel_width}
pixel_height = {pixel_height}

# Optimization settings
# Use temporary file caching
use_projection_with_camera_boundary = True

# Disable sound feedback during rendering to save processing
sound = False

# Auto-config for LaTeX
# If LaTeX is missing, this config will be overridden in command line, 
# but we disable LaTeX if not available.
text_to_speech = False
"""
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(cfg_content)
        return True
    except Exception:
        return False

if __name__ == "__main__":
    # Test output when run directly
    import json
    print(json.dumps(generate_profile(), indent=2))
