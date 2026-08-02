import torch
import warnings

# Monkey-Patch für PyTorch >= 2.6: Pyannote/WhisperX stürzen sonst beim Laden
# von VAD-Modellen ab, weil PyTorch 2.6 standardmäßig weights_only=True erzwingt.
_original_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs["weights_only"] = False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _original_load(*args, **kwargs)
torch.load = _patched_load

import whisperx
import gc
import subprocess
import imageio_ffmpeg
import numpy as np
from pathlib import Path
from rich.console import Console

def load_audio_safe(file: str, sr: int = 16000):
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-nostdin",
        "-threads", "0",
        "-i", file,
        "-f", "s16le",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-ar", str(sr),
        "-"
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to load audio: {e.stderr.decode('utf-8', errors='ignore')}") from e

    return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

from models import WordTimestamp

console = Console()

class VocalTranscriber:
    def __init__(self, device: str, model_name: str = "base"):
        self.device = device
        self.model_name = model_name
        
        # Bestimme compute_type dynamisch
        if self.device == "cuda":
            self.compute_type = "float16" # Int8 ebenfalls möglich, falls VRAM knapp ist
        else:
            # cpu oder mps -> CTranslate2 unterstützt oft kein float16 
            # (insbesondere nicht auf der CPU), daher zwingend int8
            self.compute_type = "int8"
            
        console.print(f"[cyan]Initialisiere WhisperX Transcriber...[/cyan]")
        console.print(f"Modell: {self.model_name} | Angefragtes Device: {self.device} | Compute Type: {self.compute_type}")
        
    def transcribe_and_align(self, vocal_path: Path) -> list[WordTimestamp]:
        console.print(f"[cyan]Starte Transkription für:[/cyan] {vocal_path.name}")
        
        # WhisperX/CTranslate2 erwartet als Device "cuda" oder "cpu".
        # "mps" wird nativ oft nicht sauber unterstützt, daher erzwingen wir den CPU-Fallback für WhisperX.
        wx_device = "cpu" if self.device == "mps" else self.device
        
        # 1. Laden des WhisperX Modells
        console.print(f"Lade Transkriptions-Modell '{self.model_name}'...")
        model = whisperx.load_model(self.model_name, wx_device, compute_type=self.compute_type)
        
        # Audio laden
        audio = load_audio_safe(str(vocal_path))
        
        # 2. Transkription
        console.print("Transkribiere Audiospur...")
        result = model.transcribe(audio, batch_size=16) # batch_size für bessere Performance (bei CUDA)
        language = result["language"]
        console.print(f"[green]Transkription abgeschlossen (Erkannte Sprache: {language}).[/green]")
        
        # 3. Alignment
        console.print("Lade Alignment-Modell und synchronisiere Wörter...")
        # Lade passendes Alignment-Modell zur erkannten Sprache
        model_a, metadata = whisperx.load_align_model(language_code=language, device=wx_device)
        
        # Führe Alignment aus
        aligned_result = whisperx.align(
            result["segments"], 
            model_a, 
            metadata, 
            audio, 
            wx_device, 
            return_char_alignments=False
        )
        
        # 4. Parsing der Segmente
        word_timestamps: list[WordTimestamp] = []
        for segment in aligned_result["segments"]:
            for word_info in segment.get("words", []):
                # Prüfen, ob Start- und Endzeitpunkt vorhanden sind 
                # (Satzzeichen oder sehr undeutliche Füllwörter fehlen manchmal)
                if "start" in word_info and "end" in word_info:
                    word_timestamps.append(
                        WordTimestamp(
                            word=word_info["word"],
                            start=word_info["start"],
                            end=word_info["end"]
                        )
                    )
                    
        console.print(f"[bold green]Alignment abgeschlossen! {len(word_timestamps)} gültige Wörter synchronisiert.[/bold green]")
        
        # Aufräumen: Modelle aus dem Speicher entfernen, um Platz (VRAM/RAM) für das FFmpeg Rendering freizugeben
        del model
        del model_a
        gc.collect()
        
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
            
        return word_timestamps
