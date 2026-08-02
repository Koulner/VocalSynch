import subprocess
import imageio_ffmpeg
from typing import Optional
from pathlib import Path
from rich.console import Console

console = Console()

def get_ffmpeg_encoder() -> str:
    """Ermittelt den besten verfügbaren Hardware-Encoder in FFmpeg."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        # Abfrage der Encoder über ffmpeg
        result = subprocess.run([ffmpeg_exe, "-encoders"], capture_output=True, text=True, check=True)
        output = result.stdout
        
        # Hardware-Encoder Check
        if "h264_nvenc" in output:
            return "h264_nvenc"       # NVIDIA
        elif "h264_videotoolbox" in output:
            return "h264_videotoolbox" # Apple Silicon
        elif "h264_amf" in output:
            return "h264_amf"         # AMD
    except FileNotFoundError:
        pass
    except subprocess.CalledProcessError:
        pass
        
    # Standard Software Fallback
    return "libx264"

class VideoRenderer:
    def __init__(self):
        self.encoder = get_ffmpeg_encoder()
        
    def render(self, instrumental_path: Path, ass_path: Path, output_path: Path, bg_visual: Optional[Path] = None) -> Path:
        console.print(f"[cyan]Starte Video-Rendering mit Encoder: {self.encoder}...[/cyan]")
        
        # FFmpeg Subtitle-Filter Pfad fixen für Windows (Slashes statt Backslashes und Doppelpunkt escapen)
        ass_str = str(ass_path.absolute()).replace("\\", "/")
        ass_str = ass_str.replace(":", "\\:")
        
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        command = [
            ffmpeg_exe,
            "-y", # Bestehende Ausgabedatei überschreiben
        ]
        
        if bg_visual:
            video_extensions = [".mp4", ".mkv", ".mov", ".avi", ".webm"]
            if bg_visual.suffix.lower() in video_extensions:
                # Der Hintergrund ist das Original-Video!
                command.extend([
                    "-i", str(bg_visual)
                ])
                filter_complex = f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p,subtitles='{ass_str}'[v]"
            else:
                # Der Hintergrund ist ein statisches Bild (wird geloopt)
                command.extend([
                    "-loop", "1",
                    "-framerate", "30",
                    "-i", str(bg_visual)
                ])
                filter_complex = f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p,subtitles='{ass_str}'[v]"
        else:
            # Kein Bild/Video übergeben -> lavfi-Filter generiert einen schwarzen Hintergrund
            command.extend([
                "-f", "lavfi",
                "-i", "color=c=black:s=1920x1080:r=30"
            ])
            filter_complex = f"[0:v]format=yuv420p,subtitles='{ass_str}'[v]"
            
        command.extend([
            "-i", str(instrumental_path),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a",           # Instrumental Audio track mappen
            "-c:v", self.encoder,
            "-c:a", "aac",           # Sicherstellen, dass Audio sauber für MP4 codiert wird
            "-shortest",             # Beenden, wenn Instrumental-Spur vorbei ist
            str(output_path)
        ])
        
        console.print(f"[dim]Führe FFmpeg aus: {' '.join(command)}[/dim]")
        
        try:
            subprocess.run(command, check=True)
            console.print("[bold green]Video-Rendering erfolgreich abgeschlossen![/bold green]")
        except subprocess.CalledProcessError as e:
            if self.encoder != "libx264":
                console.print(f"\n[bold yellow]Hardware-Encoder '{self.encoder}' fehlgeschlagen (evtl. fehlen Treiber wie nvcuda.dll).[/bold yellow]")
                console.print("[bold yellow]Wechsle automatisch zum Fallback-Encoder (libx264/CPU)...[/bold yellow]")
                
                # Ersetze den Encoder im Command
                try:
                    idx = command.index("-c:v")
                    command[idx+1] = "libx264"
                except ValueError:
                    pass
                
                console.print(f"[dim]Führe FFmpeg aus (Fallback): {' '.join(command)}[/dim]")
                try:
                    subprocess.run(command, check=True)
                    console.print("[bold green]Video-Rendering (CPU Fallback) erfolgreich abgeschlossen![/bold green]")
                except subprocess.CalledProcessError as e_fallback:
                    raise RuntimeError("Auch der CPU-Fallback ist beim Rendern fehlgeschlagen.")
            else:
                raise RuntimeError("Beim Rendern mit FFmpeg ist ein Fehler aufgetreten.")
            
        return output_path
