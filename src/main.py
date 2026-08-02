import typer
import subprocess
import imageio_ffmpeg
from typing import Optional
from pathlib import Path

from src.core.utils import logger, get_optimal_device
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

    def _separate_stems(self) -> dict[str, Path]:
        stemmer = AudioStemmer(config=self.config, device=self.device)
        return stemmer.separate_stems(self.input_path, self.output_dir)

    def _transcribe_and_align(self, vocal_path: Path) -> list[WordTimestamp]:
        transcriber = VocalTranscriber(config=self.config, device=self.device)
        return transcriber.transcribe_and_align(vocal_path)

    def _render_video(self, instrumental_path: Path, timestamps: list[WordTimestamp]) -> Path:
        renderer = VideoRenderer(config=self.config)
        ass_path = self.output_dir / "karaoke.ass"
        
        original_name = self.bg_visual.stem if self.bg_visual else self.input_path.stem
        output_mp4 = self.output_dir / f"{original_name}_videoke.mp4"
        
        logger.info("[cyan]Generiere ASS-Untertitel...[/cyan]")
        generate_karaoke_ass(timestamps, ass_path, config=self.config)
        
        renderer.render(instrumental_path, ass_path, output_mp4, bg_visual=self.bg_visual)
        
        return output_mp4

    def run(self):
        """
        Orchestriert die Pipeline schrittweise. (Yields strings for UI updates)
        """
        try:
            yield "Schritt 1: Stem-Separation (Audio isolieren)..."
            logger.info("\n[bold]Schritt 1: Stem-Separation[/bold]")
            stems = self._separate_stems()
            
            vocals_path = stems.get("vocals")
            instrumental_path = stems.get("instrumental")
            
            if not vocals_path or not instrumental_path:
                raise ValueError("Stem-Separation hat nicht die erwarteten Pfade zurückgegeben.")

            yield "Schritt 2: Transkription & Alignment (WhisperX)..."
            logger.info("\n[bold]Schritt 2: Transkription & Alignment[/bold]")
            timestamps = self._transcribe_and_align(vocals_path)
            
            if not timestamps:
                raise RuntimeError("Keine gültigen Timestamps generiert. Abbruch.")

            yield "Schritt 3: Video rendern (FFmpeg)..."
            logger.info("\n[bold]Schritt 3: Video-Rendering[/bold]")
            final_video_path = self._render_video(instrumental_path, timestamps)
            
            logger.info(
                f"\n[bold green]🎉 Pipeline erfolgreich abgeschlossen![/bold green]\n"
                f"Video gespeichert unter: [cyan]{final_video_path}[/cyan]"
            )
            
            yield {
                "video": final_video_path,
                "instrumental": instrumental_path,
                "ass": self.output_dir / "karaoke.ass"
            }

        except Exception as e:
            logger.info(f"\n[bold red]Pipeline-Fehler:[/bold red] {str(e)}")
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
        for status in pipeline.run():
            pass
    except Exception:
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
