import yt_dlp
from pathlib import Path
from src.core.utils import logger
import imageio_ffmpeg
import sys
import winreg

def get_default_browser() -> str:
    """Versucht, den Standardbrowser des Systems zu erkennen (Windows)."""
    if sys.platform != "win32":
        return "chrome" # Fallback für Mac/Linux
        
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice')
        prog_id, _ = winreg.QueryValueEx(key, 'ProgId')
        prog_id = prog_id.lower()
        
        if "chrome" in prog_id: return "chrome"
        if "firefox" in prog_id: return "firefox"
        if "edge" in prog_id or "msedge" in prog_id: return "edge"
        if "brave" in prog_id: return "brave"
        if "opera" in prog_id: return "opera"
        if "vivaldi" in prog_id: return "vivaldi"
    except Exception:
        pass
        
    return "chrome" # Globaler Fallback

class YouTubeDownloader:
    """
    Lädt Audio oder Video von YouTube herunter via yt-dlp.
    """
    def __init__(self):
        self.ffmpeg_exe = str(imageio_ffmpeg.get_ffmpeg_exe())

    def download(self, url: str, output_dir: Path, video_mode: bool = False) -> Path:
        """
        Lädt die URL herunter.
        Wenn video_mode=True: Lade bestes Video+Audio als MP4 herunter.
        Wenn video_mode=False: Lade bestes Audio als WAV herunter.
        """
        logger.info(f"[cyan]Starte YouTube Download für:[/cyan] {url}")
        
        ydl_opts = {
            'outtmpl': str(output_dir / '%(title)s.%(ext)s'),
            'ffmpeg_location': self.ffmpeg_exe,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extractor_args': {'youtube': ['player_client=tv,mweb']},
            # 'cookiesfrombrowser': (browser, ),
        }
        
        if video_mode:
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4'
            ydl_opts['merge_output_format'] = 'mp4'
        else:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }]
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("[dim]Lade Metadaten...[/dim]")
            info_dict = ydl.extract_info(url, download=True)
            
            # yt-dlp reinigt Dateinamen (Entfernt Sonderzeichen)
            # Wir holen uns stattdessen direkt die finale Dateibezeichnung, die ydl uns meldet
            filename = ydl.prepare_filename(info_dict)
            
            # Postprocessor ändert bei Audio ggf. die Endung auf .wav
            if not video_mode:
                filename = str(Path(filename).with_suffix('.wav'))
                
            final_path = Path(filename)
            logger.info(f"[bold green]Download erfolgreich:[/bold green] {final_path.name}")
            return final_path
