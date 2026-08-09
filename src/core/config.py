from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import yaml

class AudioConfig(BaseModel):
    """Konfiguration für die Audio-Verarbeitung (Stem-Separation)."""
    demucs_model: str = "htdemucs"

class TextConfig(BaseModel):
    """Konfiguration für die Text-Transkription (WhisperX)."""
    whisper_model: str = "base"
    hf_token: Optional[str] = None
    use_syllables: bool = False
    translation_target: str = "en"

class AssConfig(BaseModel):
    """Logische Konfiguration für das Untertitel-Timing."""
    lead_time_seconds: float = 1.5
    max_words_per_line: int = 14
    max_pause_seconds: float = 1.2
    use_entry_cues: bool = True
    play_res_x: int = 1280
    play_res_y: int = 720
    animation_style: str = "TikTok Pop-Up"

class StyleConfig(BaseModel):
    """Visuelle Konfiguration für die Untertitel-Darstellung (ASS Format)."""
    font_size: int = 36
    primary_colour: str = "&H0000FFFF"
    secondary_colour: str = "&H00FFFFFF"
    outline: int = 3
    shadow: int = 2
    margin_v: int = 15
    duet_colours: List[str] = ["&H00FFFF00", "&H00FF00FF", "&H0000FFFF", "&H0000FF00"]

class VideoConfig(BaseModel):
    """Konfiguration für das Rendering und die Videoverarbeitung."""
    downscale_1080p: bool = False
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
