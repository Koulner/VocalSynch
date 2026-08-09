import typer
import subprocess
import imageio_ffmpeg
from typing import Optional
import sys
from pathlib import Path
import copy

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.utils import logger, get_optimal_device, get_video_metadata
from src.core.config import VideokeConfig
from src.models.domain import WordTimestamp
from src.audio.stemmer import AudioStemmer
from src.text.transcriber import VocalTranscriber
from src.video.ass_writer import generate_karaoke_ass
from src.video.renderer import VideoRenderer

app = typer.Typer(help="Automatisierter Videoke-Generator (Audio/Video -> Stemming -> WhisperX -> FFmpeg)")

def prepare_input(input_path: Path, output_dir: Path) -> tuple[Path, Optional[Path]]:
    """
    Prüft, ob die Eingabe ein Video ist.
    Wenn ja, wird das Audio extrahiert und das Original-Video als Hintergrund verwendet.
    """
    video_extensions = [".mp4", ".mkv", ".mov", ".avi", ".webm"]
    if input_path.suffix.lower() in video_extensions:
        logger.info(f"[cyan]Videodatei erkannt. Extrahiere Audiospur aus {input_path.name}...[/cyan]")
        extracted_audio_path = output_dir / f"{input_path.stem}_audio.wav"
        
        if not extracted_audio_path.exists():
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            command = [
                ffmpeg_exe, "-y", "-i", str(input_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100",
                str(extracted_audio_path)
            ]
            try:
                subprocess.run(command, check=True, capture_output=True)
                logger.info("[bold green]Audiospur erfolgreich für die Bearbeitung extrahiert![/bold green]")
            except FileNotFoundError:
                raise RuntimeError("FFmpeg wurde nicht gefunden! Bitte installiere FFmpeg auf deinem System.")
            except subprocess.CalledProcessError as e:
                logger.info(f"[bold red]Fehler bei der Audio-Extraktion:[/bold red]\n{e.stderr.decode('utf-8', errors='ignore')}")
                raise RuntimeError("Konnte Audiospur nicht aus dem Video extrahieren.")
        else:
            logger.info("[dim]Audiospur bereits extrahiert, überspringe Extraktion...[/dim]")
            
        return extracted_audio_path, input_path
        
    return input_path, None

class VideokePipeline:
    def __init__(self, config: VideokeConfig, input_path: Path, output_dir: Path, bg_visual: Optional[Path] = None):
        self.config = config
        self.input_path = input_path
        self.output_dir = output_dir
        self.bg_visual = bg_visual
        self.device = get_optimal_device()
        
        logger.info(
            f"[bold green]Videoke Pipeline initialisiert[/bold green]\n"
            f"Eingabedatei: [cyan]{self.input_path}[/cyan]\n"
            f"Hintergrund:  [cyan]{self.bg_visual if self.bg_visual else 'Schwarz'}[/cyan]\n"
            f"Zielordner:   [cyan]{self.output_dir}[/cyan]\n"
            f"Gerät:        [bold yellow]{self.device}[/bold yellow]"
        )

    def run_extraction(self, keep_vocals: bool = False):
        """
        Führt Phase 1 aus: Stem-Separation und Transkription.
        Yields Statusstrings und am Ende ein dict mit instrumental_path und timestamps.
        """
        try:
            if keep_vocals:
                yield "Schritt 1: Stem-Separation übersprungen (Bypass aktiv)..."
                logger.info("\n[bold]Schritt 1: Stem-Separation (Bypass aktiv)[/bold]")
                vocals_path = self.input_path
                instrumental_path = self.input_path
            else:
                yield "Schritt 1: Stem-Separation (Audio isolieren)..."
                logger.info("\n[bold]Schritt 1: Stem-Separation[/bold]")
                
                stemmer = AudioStemmer(config=self.config, device=self.device)
                stems = stemmer.separate_stems(self.input_path, self.output_dir)
                
                vocals_path = stems.get("vocals")
                instrumental_path = stems.get("instrumental")
                
                if not vocals_path or not instrumental_path:
                    raise ValueError("Stem-Separation hat nicht die erwarteten Pfade zurückgegeben.")

            yield "Schritt 2: Transkription & Alignment (WhisperX)..."
            logger.info("\n[bold]Schritt 2: Transkription & Alignment[/bold]")
            
            transcriber = VocalTranscriber(config=self.config, device=self.device)
            timestamps = transcriber.transcribe_and_align(vocals_path)
            
            if not timestamps:
                raise RuntimeError("Keine gültigen Timestamps generiert. Abbruch.")

            yield {
                "instrumental": instrumental_path,
                "timestamps": timestamps,
                "vocals": vocals_path
            }

        except Exception as e:
            logger.info(f"\n[bold red]Pipeline-Fehler (Extraction):[/bold red] {str(e)}")
            raise e

    def run_rendering(self, instrumental_path: Path, timestamps: list[WordTimestamp], override_config: Optional[VideokeConfig] = None, use_original_video: bool = False, project_name: str = None):
        """
        Führt Phase 2 aus: Video rendern mit editierten Timestamps und Config.
        """
        try:
            yield "Schritt 3: Video rendern (FFmpeg)..."
            logger.info("\n[bold]Schritt 3: Video-Rendering[/bold]")
            
            active_config = override_config if override_config else self.config
            
            # Auflösung des Hintergrunds ermitteln
            target_w, target_h = 1280, 720
            if self.bg_visual:
                meta = get_video_metadata(self.bg_visual)
                if meta.get("width") and meta.get("height"):
                    target_w = meta["width"]
                    target_h = meta["height"]
                    
            if active_config.video.downscale_1080p:
                logger.info("[cyan]Smart Downscaling (max 1080p) aktiv...[/cyan]")
                if target_w > target_h and target_w > 1920:
                    scale = 1920 / target_w
                    target_w = 1920
                    target_h = int(target_h * scale)
                elif target_h > target_w and target_h > 1920:
                    scale = 1920 / target_h
                    target_h = 1920
                    target_w = int(target_w * scale)
                    
            # Canvas-Auflösung in Config speichern
            active_config.video.ass.play_res_x = target_w
            active_config.video.ass.play_res_y = target_h
            
            renderer = VideoRenderer(config=active_config)
            ass_path = self.output_dir / "karaoke.ass"
            
            if project_name:
                from src.core.project_manager import sanitize_filename
                safe_name = sanitize_filename(project_name)
                output_mp4 = self.output_dir / f"{safe_name}.mp4"
            else:
                original_name = self.bg_visual.stem if self.bg_visual else self.input_path.stem
                output_mp4 = self.output_dir / f"{original_name}_videoke.mp4"
            
            logger.info(f"[cyan]Generiere ASS-Untertitel (Canvas: {target_w}x{target_h})...[/cyan]")
            generate_karaoke_ass(timestamps, ass_path, config=active_config)
            
            renderer.render(instrumental_path, ass_path, output_mp4, bg_visual=self.bg_visual, use_original_video=use_original_video)
            
            logger.info(
                f"\n[bold green]🎉 Pipeline erfolgreich abgeschlossen![/bold green]\n"
                f"Video gespeichert unter: [cyan]{output_mp4}[/cyan]"
            )
            
            yield {
                "video": output_mp4,
                "instrumental": instrumental_path,
                "ass": ass_path
            }

        except Exception as e:
            logger.info(f"\n[bold red]Pipeline-Fehler (Rendering):[/bold red] {str(e)}")
            raise e

@app.command()
def main(
    input_path: Path = typer.Option(..., "--input", "-i", help="Pfad zur Datei", exists=True, dir_okay=False),
    output_dir: Path = typer.Option(..., "--output-dir", "-o", help="Zielordner", file_okay=False),
    config_path: str = typer.Option("configs/default.yaml", "--config", "-c", help="Pfad zur config.yaml")
):
    """
    Startet den Prozess, um aus einer MP3 oder MP4 ein Videoke-Video zu generieren.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    config = VideokeConfig.load(config_path)
    actual_audio, bg_visual = prepare_input(input_path, output_dir)
    
    pipeline = VideokePipeline(config=config, input_path=actual_audio, output_dir=output_dir, bg_visual=bg_visual)
    
    try:
        # Phase 1
        instrumental_path = None
        timestamps = []
        for status in pipeline.run_extraction():
            if isinstance(status, dict):
                instrumental_path = status["instrumental"]
                timestamps = status["timestamps"]
        
        # Phase 2
        for status in pipeline.run_rendering(instrumental_path, timestamps):
            pass
            
    except Exception:
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
