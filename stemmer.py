import subprocess
import shutil
from pathlib import Path
from rich.console import Console

from utils import is_amd_rocm

console = Console()

class AudioStemmer:
    def __init__(self, device: str):
        self.device = device
        
        if self.device == "cuda":
            if is_amd_rocm():
                console.print("[bold green]GPU erkannt, starte Demucs CLI auf CUDA/ROCm (AMD)...[/bold green]")
                self.demucs_device = "cuda"
            else:
                console.print("[bold green]GPU erkannt, starte Demucs CLI auf CUDA (NVIDIA)...[/bold green]")
                self.demucs_device = "cuda"
        elif self.device == "mps":
            console.print("[bold green]GPU erkannt, starte Demucs CLI auf CPU (MPS Fallback, um Crashes zu vermeiden)...[/bold green]")
            self.demucs_device = "cpu"
        else:
            console.print("[bold yellow]Warnung: Nur CPU verfügbar, Trennung kann dauern...[/bold yellow]")
            self.demucs_device = "cpu"

    def separate_stems(self, input_path: Path, output_dir: Path) -> dict[str, Path]:
        console.print(f"[cyan]Trenne Audio-Stems für:[/cyan] {input_path}")
        
        # Demucs über CLI aufrufen statt über die fehleranfällige Python-API.
        # --two-stems vocals isoliert direkt die Vocals und mischt den Rest als no_vocals.wav zusammen!
        command = [
            "demucs",
            "--two-stems", "vocals",
            "-n", "htdemucs",
            "-o", str(output_dir),
            "-d", self.demucs_device,
            str(input_path)
        ]
        
        console.print(f"[dim]Führe Demucs-Prozess aus: {' '.join(command)}[/dim]")
        
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Beim Ausführen von Demucs ist ein Fehler aufgetreten:\n{e}")
            
        # Demucs speichert die Dateien unter: output_dir / "htdemucs" / input_filename /
        demucs_out_dir = output_dir / "htdemucs" / input_path.stem
        
        original_vocals = demucs_out_dir / "vocals.wav"
        original_instrumental = demucs_out_dir / "no_vocals.wav"
        
        final_vocals = output_dir / "vocals.wav"
        final_instrumental = output_dir / "instrumental.wav"
        
        # Verschiebe die fertigen Stems in das saubere Output-Directory
        if original_vocals.exists():
            # Überschreibe, falls existiert (mit shutil.move bei existierendem Ziel manchmal problematisch, 
            # daher nutzen wir copy + remove oder path.replace)
            original_vocals.replace(final_vocals)
        else:
            raise FileNotFoundError(f"Demucs hat {original_vocals} nicht erstellt.")
            
        if original_instrumental.exists():
            original_instrumental.replace(final_instrumental)
        else:
            raise FileNotFoundError(f"Demucs hat {original_instrumental} nicht erstellt.")
            
        # Räume den temporären htdemucs Ordner auf
        if demucs_out_dir.exists():
            shutil.rmtree(demucs_out_dir.parent, ignore_errors=True)
            
        console.print("[bold green]Stem-Separation erfolgreich abgeschlossen![/bold green]")
        
        return {
            "vocals": final_vocals.absolute(),
            "instrumental": final_instrumental.absolute()
        }
