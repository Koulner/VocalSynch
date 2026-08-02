import typer
import subprocess
import imageio_ffmpeg
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from utils import get_optimal_device
from models import WordTimestamp
from stemmer import AudioStemmer
from transcriber import VocalTranscriber
from ass_writer import generate_karaoke_ass
from renderer import VideoRenderer

app = typer.Typer(help="Automatisierter Videoke-Generator (Audio/Video -> Stemming -> WhisperX -> FFmpeg)")
console = Console()

def prepare_input(input_path: Path, output_dir: Path) -> tuple[Path, Optional[Path]]:
    """
    Prüft, ob die Eingabe ein Video ist.
    Wenn ja, wird das Audio extrahiert und das Original-Video als Hintergrund verwendet.
    Gibt (Pfad_zur_Audiospur, Pfad_zum_Hintergrundvideo) zurück.
    """
    video_extensions = [".mp4", ".mkv", ".mov", ".avi", ".webm"]
    if input_path.suffix.lower() in video_extensions:
        console.print(f"[cyan]Videodatei erkannt. Extrahiere Audiospur aus {input_path.name}...[/cyan]")
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
                console.print("[bold green]Audiospur erfolgreich für die Bearbeitung extrahiert![/bold green]")
            except FileNotFoundError:
                raise RuntimeError("FFmpeg wurde nicht gefunden! Bitte installiere FFmpeg auf deinem System (z.B. via 'winget install ffmpeg') und starte das Terminal neu.")
            except subprocess.CalledProcessError as e:
                console.print(f"[bold red]Fehler bei der Audio-Extraktion:[/bold red]\n{e.stderr.decode('utf-8', errors='ignore')}")
                raise RuntimeError("Konnte Audiospur nicht aus dem Video extrahieren.")
        else:
            console.print("[dim]Audiospur bereits extrahiert, überspringe Extraktion...[/dim]")
            
        return extracted_audio_path, input_path
        
    return input_path, None

class VideokePipeline:
    def __init__(self, input_path: Path, output_dir: Path, bg_visual: Optional[Path] = None):
        self.input_path = input_path
        self.output_dir = output_dir
        self.bg_visual = bg_visual
        self.device = get_optimal_device()
        
        console.print(Panel.fit(
            f"[bold green]Videoke Pipeline initialisiert[/bold green]\n"
            f"Eingabedatei: [cyan]{self.input_path}[/cyan]\n"
            f"Hintergrund:  [cyan]{self.bg_visual if self.bg_visual else 'Schwarz'}[/cyan]\n"
            f"Zielordner:   [cyan]{self.output_dir}[/cyan]\n"
            f"Gerät:        [bold yellow]{self.device}[/bold yellow]",
            title="Videoke-Generator"
        ))

    def _separate_stems(self) -> dict[str, Path]:
        stemmer = AudioStemmer(device=self.device)
        return stemmer.separate_stems(self.input_path, self.output_dir)

    def _transcribe_and_align(self, vocal_path: Path) -> list[WordTimestamp]:
        transcriber = VocalTranscriber(device=self.device, model_name="base")
        return transcriber.transcribe_and_align(vocal_path)

    def _render_video(self, instrumental_path: Path, timestamps: list[WordTimestamp]) -> Path:
        renderer = VideoRenderer()
        ass_path = self.output_dir / "karaoke.ass"
        
        # Name des Zielvideos basierend auf dem originalen bg_visual oder input_path
        original_name = self.bg_visual.stem if self.bg_visual else self.input_path.stem
        output_mp4 = self.output_dir / f"{original_name}_videoke.mp4"
        
        console.print("[cyan]Generiere ASS-Untertitel...[/cyan]")
        generate_karaoke_ass(timestamps, ass_path)
        
        # Aufruf des Video-Renderers
        renderer.render(instrumental_path, ass_path, output_mp4, bg_visual=self.bg_visual)
        
        return output_mp4

    def run(self):
        """
        Orchestriert die Pipeline schrittweise. (Yields strings for UI updates)
        """
        try:
            # Schritt 1: Stems separieren
            yield "Schritt 1: Stem-Separation (Audio isolieren)..."
            console.print("\n[bold]Schritt 1: Stem-Separation[/bold]")
            stems = self._separate_stems()
            
            vocals_path = stems.get("vocals")
            instrumental_path = stems.get("instrumental")
            
            if not vocals_path or not instrumental_path:
                raise ValueError("Stem-Separation hat nicht die erwarteten Pfade (vocals, instrumental) zurückgegeben.")

            # Schritt 2: Transkription & Alignment der Vocals
            yield "Schritt 2: Transkription & Alignment (WhisperX)..."
            console.print("\n[bold]Schritt 2: Transkription & Alignment[/bold]")
            timestamps = self._transcribe_and_align(vocals_path)
            
            if not timestamps:
                raise RuntimeError("Keine gültigen Timestamps generiert. Abbruch.")

            # Schritt 3: Rendern des Videos (Karaoke-Effekt)
            yield "Schritt 3: Video rendern (FFmpeg)..."
            console.print("\n[bold]Schritt 3: Video-Rendering[/bold]")
            final_video_path = self._render_video(instrumental_path, timestamps)
            
            console.print(Panel.fit(
                f"[bold green]🎉 Pipeline erfolgreich abgeschlossen![/bold green]\n\n"
                f"Video gespeichert unter:\n[cyan]{final_video_path}[/cyan]",
                title="Erfolg!"
            ))
            
            yield {
                "video": final_video_path,
                "instrumental": instrumental_path,
                "ass": self.output_dir / "karaoke.ass"
            }

        except Exception as e:
            console.print(f"\n[bold red]Pipeline-Fehler:[/bold red] {str(e)}")
            raise e


@app.command()
def main(
    input_path: Path = typer.Option(
        ..., "--input", "-i", 
        help="Pfad zur Audio- oder Videodatei (MP3, MP4, WAV, etc.)", 
        exists=True, 
        dir_okay=False
    ),
    output_dir: Path = typer.Option(
        ..., "--output-dir", "-o", 
        help="Zielordner für die generierten Dateien", 
        file_okay=False
    )
):
    """
    Startet den Prozess, um aus einer MP3 oder MP4 ein Videoke-Video zu generieren.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Bereite Eingabe vor (Audio aus Video extrahieren, falls nötig)
    actual_audio, bg_visual = prepare_input(input_path, output_dir)
    
    pipeline = VideokePipeline(input_path=actual_audio, output_dir=output_dir, bg_visual=bg_visual)
    
    try:
        for status in pipeline.run():
            if isinstance(status, str):
                pass # CLI prints are handled inside run()
    except Exception:
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
