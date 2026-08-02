import torch
from rich.console import Console
from rich.logging import RichHandler
import logging

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
