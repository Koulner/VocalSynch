import torch
from rich.console import Console
from rich.logging import RichHandler
import logging
import subprocess
import imageio_ffmpeg
import json
from pathlib import Path

# Zentrale Console-Instanz für das gesamte Projekt
console = Console()

# Logger-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console)]
)

logger = logging.getLogger("videoke")

def is_amd_rocm() -> bool:
    """
    Prüft, ob die CUDA-Version in PyTorch eigentlich eine AMD ROCm-Umgebung ist.
    """
    return hasattr(torch.version, "hip") and torch.version.hip is not None

def get_optimal_device() -> str:
    """
    Ermittelt das beste verfügbare Gerät für Berechnungen:
    - 'cuda' für NVIDIA GPUs (und AMD GPUs via ROCm)
    - 'mps' für Apple Silicon (M1/M2/M3)
    - 'cpu' als Fallback
    """
    if torch.cuda.is_available():
        return "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def get_video_metadata(video_path: Path) -> dict:
    """Holt Metadaten (Auflösung, Codec) via ffprobe."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe_exe = str(ffmpeg_exe).replace("ffmpeg", "ffprobe")
        if not Path(ffprobe_exe).exists():
            ffprobe_exe = "ffprobe" # Fallback auf systemweiten ffprobe
            
        command = [
            ffprobe_exe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name",
            "-of", "json",
            str(video_path)
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except Exception as e:
        logger.info(f"[bold yellow]ffprobe Fehler: {e}. Verwende Fallback.[/bold yellow]")
        return {}
