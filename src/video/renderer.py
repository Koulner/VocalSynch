import subprocess
import imageio_ffmpeg
from typing import Optional
from pathlib import Path
from src.core.utils import logger, get_video_metadata
from src.core.config import VideokeConfig

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
        
        is_video = bg_visual and bg_visual.suffix.lower() in [".mp4", ".mov", ".mkv", ".avi", ".webm"]
        
        play_x = self.config.video.ass.play_res_x
        play_y = self.config.video.ass.play_res_y
        vf_filter = f"scale={play_x}:{play_y},subtitles='{ass_str}'"
        
        if use_original_video and is_video:
            meta = get_video_metadata(bg_visual)
            logger.info(f"[dim]Original Video Metadaten: {meta}[/dim]")
            
            command.extend([
                "-i", str(bg_visual),
                "-i", str(instrumental_path),
                "-vf", vf_filter,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", self.encoder,
                "-c:a", "aac",
                "-shortest",
                str(output_path)
            ])
        elif bg_visual and not is_video:
            command.extend([
                "-loop", "1",
                "-i", str(bg_visual),
                "-i", str(instrumental_path),
                "-vf", vf_filter,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", self.encoder,
                "-c:a", "aac",
                "-shortest",
                str(output_path)
            ])
        elif bg_visual and is_video and not use_original_video:
            logger.info("[cyan]Verwende das erste Bild des Videos als statischen Hintergrund...[/cyan]")
            frame_path = output_path.parent / f"{bg_visual.stem}_frame.jpg"
            if not frame_path.exists():
                subprocess.run([
                    ffmpeg_exe, "-y", "-i", str(bg_visual),
                    "-vframes", "1", "-q:v", "2", str(frame_path)
                ], check=True, capture_output=True)
                
            command.extend([
                "-loop", "1",
                "-i", str(frame_path),
                "-i", str(instrumental_path),
                "-vf", vf_filter,
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
                "-i", f"color=c=black:s={play_x}x{play_y}:r=30",
                "-i", str(instrumental_path),
                "-vf", vf_filter,
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
