from pydantic import BaseModel
from pathlib import Path
import yaml

class AudioConfig(BaseModel):
    """Konfiguration für die Audio-Verarbeitung (Stem-Separation)."""
    demucs_model: str = "htdemucs"

class TextConfig(BaseModel):
    """Konfiguration für die Text-Transkription (WhisperX)."""
    whisper_model: str = "base"

class AssConfig(BaseModel):
    """Logische Konfiguration für das Untertitel-Timing."""
    lead_time_seconds: float = 1.5
    max_words_per_line: int = 14
    max_pause_seconds: float = 1.2

class StyleConfig(BaseModel):
    """Visuelle Konfiguration für die Untertitel-Darstellung (ASS Format)."""
    font_size: int = 36
    primary_colour: str = "&H0000FFFF"
    secondary_colour: str = "&H00FFFFFF"
    outline: int = 3
    shadow: int = 2

class VideoConfig(BaseModel):
    """Konfiguration für das Rendering und die Videoverarbeitung."""
    ass: AssConfig
    style: StyleConfig

class VideokeConfig(BaseModel):
    """Zentrale Konfigurationsklasse für die Videoke-Pipeline."""
    audio: AudioConfig
    text: TextConfig
    video: VideoConfig

    @classmethod
    def load(cls, config_path: str = "configs/default.yaml") -> "VideokeConfig":
        """
        Lädt die Konfiguration aus einer YAML-Datei und validiert sie via Pydantic.
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path.absolute()}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
        return cls(**data)
