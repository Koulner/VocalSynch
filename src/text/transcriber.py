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

from src.core.utils import logger
from src.core.config import VideokeConfig
from src.models.domain import WordTimestamp

def load_audio_safe(file: str, sr: int = 16000):
    """
    Sicheres Laden von Audio ohne System-FFmpeg Abhängigkeit.
    """
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

class VocalTranscriber:
    """
    Führt Transkription und wortgenaues Alignment der isolierten Vocals durch.
    """
    def __init__(self, config: VideokeConfig, device: str):
        self.config = config
        self.device = device
        
        # Bestimme compute_type dynamisch
        if self.device == "cuda":
            self.compute_type = "float16"
        else:
            self.compute_type = "int8"
            
        logger.info("[cyan]Initialisiere WhisperX Transcriber...[/cyan]")
        logger.info(f"Modell: {self.config.text.whisper_model} | Angefragtes Device: {self.device} | Compute Type: {self.compute_type}")
        
    def transcribe_and_align(self, vocal_path: Path) -> list[WordTimestamp]:
        """
        Liest das Audio, transkribiert es und führt ein Alignment durch.
        """
        logger.info(f"[cyan]Starte Transkription für:[/cyan] {vocal_path.name}")
        
        wx_device = "cpu" if self.device == "mps" else self.device
        
        logger.info(f"Lade Transkriptions-Modell '{self.config.text.whisper_model}'...")
        model = whisperx.load_model(self.config.text.whisper_model, wx_device, compute_type=self.compute_type)
        
        audio = load_audio_safe(str(vocal_path))
        
        logger.info("Transkribiere Audiospur...")
        result = model.transcribe(audio, batch_size=16)
        language = result["language"]
        logger.info(f"[green]Transkription abgeschlossen (Erkannte Sprache: {language}).[/green]")
        
        logger.info("Lade Alignment-Modell und synchronisiere Wörter...")
        model_a, metadata = whisperx.load_align_model(language_code=language, device=wx_device)
        
        aligned_result = whisperx.align(
            result["segments"], 
            model_a, 
            metadata, 
            audio, 
            wx_device, 
            return_char_alignments=False
        )
        
        # Diarization falls hf_token gesetzt
        if self.config.text.hf_token:
            logger.info("[cyan]Führe Speaker Diarization aus...[/cyan]")
            try:
                diarize_model = whisperx.DiarizationPipeline(use_auth_token=self.config.text.hf_token, device=wx_device)
                diarize_segments = diarize_model(audio)
                aligned_result = whisperx.assign_word_speakers(diarize_segments, aligned_result)
                logger.info("[bold green]Diarization abgeschlossen.[/bold green]")
            except Exception as e:
                logger.info(f"[bold yellow]Diarization fehlgeschlagen (Falscher Token / keine Rechte?): {str(e)}[/bold yellow]")

        word_timestamps: list[WordTimestamp] = []
        for segment in aligned_result["segments"]:
            speaker = segment.get("speaker")
            for word_info in segment.get("words", []):
                if "start" in word_info and "end" in word_info:
                    word_speaker = word_info.get("speaker", speaker)
                    word_timestamps.append(
                        WordTimestamp(
                            word=word_info["word"],
                            start=word_info["start"],
                            end=word_info["end"],
                            speaker=word_speaker
                        )
                    )
                    
        logger.info(f"[bold green]Alignment abgeschlossen! {len(word_timestamps)} gültige Wörter synchronisiert.[/bold green]")
        
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
