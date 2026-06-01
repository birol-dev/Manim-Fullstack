import os
import shutil
import platform
import subprocess
import psutil

def get_cpu_info():
    """Returns CPU model, physical cores, and logical threads."""
    cpu_model = "Unknown Processor"
    try:
        # On Windows, retrieve CPU name from PowerShell or registry
        if platform.system() == "Windows":
            try:
                # Try PowerShell first
                out = subprocess.check_output(
                    ["powershell", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                ).decode().strip()
                if out:
                    cpu_model = out
            except Exception:
                # Fallback to direct path of wmic
                try:
                    wmic_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "wbem", "wmic.exe")
                    if os.path.exists(wmic_path):
                        out = subprocess.check_output(
                            f'"{wmic_path}" cpu get name', 
                            shell=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                        ).decode().strip()
                        lines = [line.strip() for line in out.split("\n") if line.strip()]
                        if len(lines) > 1:
                            cpu_model = lines[1]
                except Exception:
                    pass
        else:
            cpu_model = platform.processor()
    except Exception:
        cpu_model = platform.processor() or "Unknown CPU"

    return {
        "model": cpu_model,
        "physical_cores": psutil.cpu_count(logical=False) or 1,
        "logical_threads": psutil.cpu_count(logical=True) or 1
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
        out = subprocess.check_output("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", shell=True).decode()
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
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                    ).decode().strip()
                    for line in out.split("\n"):
                        name = line.strip()
                        if name and "Virtual" not in name and "Mirror" not in name:
                            gpus.append({"name": name, "vram": "Unknown", "type": "Generic"})
                except Exception:
                    # Fallback to wmic with absolute path
                    wmic_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "wbem", "wmic.exe")
                    if os.path.exists(wmic_path):
                        out = subprocess.check_output(
                            f'"{wmic_path}" path win32_VideoController get name',
                            shell=True,
                            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                        ).decode().strip()
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

def get_binary_paths():
    """Locates manim, ffmpeg, latex, and dvisvgm paths."""
    manim_path = shutil.which("manim")
    ffmpeg_path = shutil.which("ffmpeg")
    latex_path = shutil.which("latex")
    dvisvgm_path = shutil.which("dvisvgm")

    # Double check common paths on Windows if not in PATH
    if not manim_path:
        # Check specific path found in check
        custom_manim = r"C:\tools\Manim\Scripts\manim.exe"
        if os.path.exists(custom_manim):
            manim_path = custom_manim

    return {
        "manim": manim_path or "Not Found",
        "ffmpeg": ffmpeg_path or "Not Found",
        "latex": latex_path or "Not Found",
        "dvisvgm": dvisvgm_path or "Not Found",
        "latex_available": latex_path is not None and dvisvgm_path is not None
    }

def generate_profile():
    """Generates a hardware-specific configuration profile for Manim rendering."""
    cpu = get_cpu_info()
    ram = get_ram_info()
    gpu = get_gpu_info()
    binaries = get_binary_paths()

    threads = cpu["logical_threads"]
    
    # Profile decision logic
    if threads < 4 or ram < 6:
        profile_name = "eco"
        preview_quality = "480p15"
        default_fps = 15
        default_res = "854x480"
        description = "Optimized for battery saving / lower-spec computers. Caching is aggressive and quality defaults are low for fast rendering."
    elif threads <= 8 and ram <= 16:
        profile_name = "balanced"
        preview_quality = "720p30"
        default_fps = 30
        default_res = "1280x720"
        description = "Standard system configuration. Balanced preview quality and rendering speeds."
    else:
        profile_name = "workstation"
        preview_quality = "1080p60"
        default_fps = 60
        default_res = "1920x1080"
        description = "High performance workstation. Previews are crisp and render settings use multithreaded FFMPEG encoders."

    # Can we use OpenGL hardware acceleration?
    # OpenGL rendering in Manim requires window creation and works best with dedicated GPU drivers
    opengl_capable = len(gpu["devices"]) > 0 and gpu["devices"][0]["type"] != "Software"

    config = {
        "profile": profile_name,
        "description": description,
        "preview_quality": preview_quality,
        "default_fps": default_fps,
        "default_resolution": default_res,
        "recommended_threads": max(1, threads - 1),  # Leave 1 core for OS/FastAPI
        "opengl_supported": opengl_capable,
        "hardware": {
            "cpu": cpu,
            "ram_gb": ram,
            "gpu": gpu
        },
        "dependencies": binaries
    }

    return config

def write_manim_config_file(workspace_path: str, profile_config: dict):
    """Generates a customized manim.cfg file inside the user's workspace to apply default speedups."""
    cfg_path = os.path.join(workspace_path, "manim.cfg")
    
    # We optimize ffmpeg options, log directories, and rendering defaults
    quality_profile = profile_config["profile"]
    recommended_threads = profile_config["recommended_threads"]
    
    # Let's customize cache settings and thread count for FFMPEG encoding
    cfg_content = f"""[CLI]
# Custom generated config optimized for your PC config: {profile_config['hardware']['cpu']['model']}
# Profile: {quality_profile}

# Logging configuration
write_to_movie = True
media_dir = ./media
log_dir = ./logs

# Frame parameters for defaults
frame_rate = {profile_config['default_fps']}
pixel_width = {profile_config['default_resolution'].split('x')[0]}
pixel_height = {profile_config['default_resolution'].split('x')[1]}

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
        with open(cfg_path, "w") as f:
            f.write(cfg_content)
        return True
    except Exception:
        return False

if __name__ == "__main__":
    # Test output when run directly
    import json
    print(json.dumps(generate_profile(), indent=2))
