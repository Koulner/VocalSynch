import subprocess
import imageio_ffmpeg
from typing import Optional
from pathlib import Path
from src.core.utils import logger
from src.core.config import VideokeConfig
import json

def get_ffmpeg_encoder() -> str:
    """Ermittelt den besten verfügbaren Hardware-Encoder in FFmpeg."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run([ffmpeg_exe, "-encoders"], capture_output=True, text=True, check=True)
        output = result.stdout
        
        if "h264_nvenc" in output:
            return "h264_nvenc"
        elif "h264_videotoolbox" in output:
            return "h264_videotoolbox"
        elif "h264_amf" in output:
            return "h264_amf"
            
        return "libx264"
    except Exception:
        return "libx264"

def get_video_metadata(video_path: Path) -> dict:
    """Holt Metadaten (Auflösung, Codec) via ffprobe."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe_exe = str(ffmpeg_exe).replace("ffmpeg", "ffprobe")
        if not Path(ffprobe_exe).exists():
            ffprobe_exe = "ffprobe" # Fallback auf systemweiten ffprobe
            
        command = [
            ffprobe_exe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name",
            "-of", "json",
            str(video_path)
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except Exception as e:
        logger.info(f"[bold yellow]ffprobe Fehler: {e}. Verwende Fallback.[/bold yellow]")
        return {}

class VideoRenderer:
    """
    Rendert das finale MP4-Video aus Audio und ASS-Untertiteln mittels FFmpeg.
    """
    def __init__(self, config: VideokeConfig):
        self.config = config
        self.encoder = get_ffmpeg_encoder()
        logger.info(f"[cyan]Video-Renderer initialisiert. Gewählter Encoder:[/cyan] {self.encoder}")
        
    def render(self, instrumental_path: Path, ass_path: Path, output_path: Path, bg_visual: Optional[Path] = None, use_original_video: bool = False) -> Path:
        """
        Baut das Video zusammen.
        """
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ass_str = str(ass_path).replace("\\", "/")
        ass_str = ass_str.replace(":", "\\\\:")
        
        command = [
            ffmpeg_exe,
            "-y",
        ]
        
        if use_original_video and bg_visual:
            meta = get_video_metadata(bg_visual)
            logger.info(f"[dim]Original Video Metadaten: {meta}[/dim]")
            
            command.extend([
                "-i", str(bg_visual),
                "-i", str(instrumental_path),
                "-vf", f"subtitles='{ass_str}'",
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", self.encoder,
                "-c:a", "aac",
                "-shortest",
                str(output_path)
            ])
        elif bg_visual and not use_original_video:
            command.extend([
                "-loop", "1",
                "-i", str(bg_visual),
                "-i", str(instrumental_path),
                "-vf", f"subtitles='{ass_str}'",
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", self.encoder,
                "-c:a", "aac",
                "-shortest",
                str(output_path)
            ])
        else:
            command.extend([
                "-f", "lavfi",
                "-i", "color=c=black:s=1280x720:r=30",
                "-i", str(instrumental_path),
                "-vf", f"subtitles='{ass_str}'",
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", self.encoder,
                "-c:a", "aac",
                "-shortest",
                str(output_path)
            ])
            
        logger.info(f"[dim]Führe FFmpeg aus: {' '.join(command)}[/dim]")
        
        try:
            subprocess.run(command, check=True)
            logger.info("[bold green]Video-Rendering erfolgreich abgeschlossen![/bold green]")
        except subprocess.CalledProcessError as e:
            if self.encoder != "libx264":
                logger.info(f"\n[bold yellow]Hardware-Encoder '{self.encoder}' fehlgeschlagen.[/bold yellow]")
                logger.info("[bold yellow]Wechsle automatisch zum Fallback-Encoder (libx264/CPU)...[/bold yellow]")
                
                try:
                    idx = command.index("-c:v")
                    command[idx+1] = "libx264"
                except ValueError:
                    pass
                
                logger.info(f"[dim]Führe FFmpeg aus (Fallback): {' '.join(command)}[/dim]")
                try:
                    subprocess.run(command, check=True)
                    logger.info("[bold green]Video-Rendering (CPU Fallback) erfolgreich abgeschlossen![/bold green]")
                except subprocess.CalledProcessError:
                    raise RuntimeError("Auch der CPU-Fallback ist beim Rendern fehlgeschlagen.")
            else:
                raise RuntimeError("Beim Rendern mit FFmpeg ist ein Fehler aufgetreten.")
            
        return output_path
