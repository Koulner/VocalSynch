import subprocess
import shutil
from pathlib import Path
from src.core.utils import is_amd_rocm, console, logger
from src.core.config import VideokeConfig

class AudioStemmer:
    """
    Kapselt die Logik für die Trennung von Gesang und Instrumental 
    über das Facebook Demucs CLI.
    """
    def __init__(self, config: VideokeConfig, device: str):
        self.config = config
        self.device = device
        
        if self.device == "cuda":
            if is_amd_rocm():
                logger.info("[bold green]GPU erkannt, starte Demucs CLI auf CUDA/ROCm (AMD)...[/bold green]")
                self.demucs_device = "cuda"
            else:
                logger.info("[bold green]GPU erkannt, starte Demucs CLI auf CUDA (NVIDIA)...[/bold green]")
                self.demucs_device = "cuda"
        elif self.device == "mps":
            logger.info("[bold green]GPU erkannt, starte Demucs CLI auf CPU (MPS Fallback, um Crashes zu vermeiden)...[/bold green]")
            self.demucs_device = "cpu"
        else:
            logger.info("[bold yellow]Warnung: Nur CPU verfügbar, Trennung kann dauern...[/bold yellow]")
            self.demucs_device = "cpu"

    def separate_stems(self, input_path: Path, output_dir: Path) -> dict[str, Path]:
        """
        Trennt Vocals und Instrumental aus dem Audio input_path und speichert sie in output_dir.
        """
        logger.info(f"[cyan]Trenne Audio-Stems für:[/cyan] {input_path}")
        
        command = [
            "demucs",
            "--two-stems", "vocals",
            "-n", self.config.audio.demucs_model,
            "-o", str(output_dir),
            "-d", self.demucs_device,
            str(input_path)
        ]
        
        logger.info(f"[dim]Führe Demucs-Prozess aus: {' '.join(command)}[/dim]")
        
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Beim Ausführen von Demucs ist ein Fehler aufgetreten:\n{e}")
            
        # Demucs speichert die Dateien unter: output_dir / model_name / input_filename /
        demucs_out_dir = output_dir / self.config.audio.demucs_model / input_path.stem
        
        original_vocals = demucs_out_dir / "vocals.wav"
        original_instrumental = demucs_out_dir / "no_vocals.wav"
        
        final_vocals = output_dir / "vocals.wav"
        final_instrumental = output_dir / "instrumental.wav"
        
        if original_vocals.exists():
            original_vocals.replace(final_vocals)
        else:
            raise FileNotFoundError(f"Demucs hat {original_vocals} nicht erstellt.")
            
        if original_instrumental.exists():
            original_instrumental.replace(final_instrumental)
        else:
            raise FileNotFoundError(f"Demucs hat {original_instrumental} nicht erstellt.")
            
        if demucs_out_dir.exists():
            shutil.rmtree(demucs_out_dir.parent, ignore_errors=True)
            
        logger.info("[bold green]Stem-Separation erfolgreich abgeschlossen![/bold green]")
        
        return {
            "vocals": final_vocals.absolute(),
            "instrumental": final_instrumental.absolute()
        }
