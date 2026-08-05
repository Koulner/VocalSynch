import sys
from pathlib import Path

# Fix: Setze den Root-Pfad des Projekts in den sys.path, 
# damit absolute Imports via 'src.XXX' funktionieren.
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import gradio as gr
import pandas as pd
import json
from src.main import prepare_input, VideokePipeline
from src.core.config import VideokeConfig
from src.models.domain import WordTimestamp
from src.utils.downloader import YouTubeDownloader
from src.core.project_manager import export_project, import_project

def hex_to_ass_color(hex_rgb: str) -> str:
    """Konvertiert Gradio RGB Hex (#RRGGBB) zu ASS BGR Hex (&H00BBGGRR)."""
    hex_rgb = hex_rgb.lstrip('#')
    if len(hex_rgb) == 6:
        r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"

def start_extraction(audio_input, bg_input, keep_vocals, use_original_video, is_duet, hf_token, youtube_url, use_syllables, progress=gr.Progress()):
    try:
        if not audio_input and not youtube_url:
            raise gr.Error("Bitte lade eine Audio- oder Videodatei hoch oder gib einen YouTube-Link an.")
            
        output_dir = Path("ergebnis_ui")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if youtube_url:
            progress(0.0, desc="YouTube Video wird heruntergeladen...")
            downloader = YouTubeDownloader()
            input_path = downloader.download(youtube_url, output_dir, video_mode=use_original_video)
        else:
            input_path = Path(audio_input)
            
        bg_visual = Path(bg_input) if bg_input else None
        
        progress(0.1, desc="Audio extrahieren (falls Video)...")
        actual_audio, extracted_video = prepare_input(input_path, output_dir)
        
        # Priorität: Hochgeladenes Bild > Extrahiertes Video > None
        actual_bg_visual = bg_visual if bg_visual else extracted_video
        config = VideokeConfig.load("configs/default.yaml")
        config.text.use_syllables = use_syllables
        
        if is_duet and hf_token:
            config.text.hf_token = hf_token
            
        pipeline = VideokePipeline(config=config, input_path=actual_audio, output_dir=output_dir, bg_visual=actual_bg_visual)
        
        instrumental_path = None
        timestamps = []
        vocals_path = None
        
        for status in pipeline.run_extraction(keep_vocals=keep_vocals):
            if isinstance(status, str):
                progress(0.5, desc=status)
            elif isinstance(status, dict):
                instrumental_path = status["instrumental"]
                timestamps = status["timestamps"]
                vocals_path = status.get("vocals", actual_audio)
                
        if not instrumental_path or not timestamps:
            raise gr.Error("Ein Fehler ist bei der Extraktion aufgetreten.")
            
        words_list = [{"word": wt.word, "start": wt.start, "end": wt.end, "speaker": wt.speaker or ""} for wt in timestamps]
        media_paths = {
            "Vocals": str(vocals_path),
            "Instrumental": str(instrumental_path),
            "Original": str(actual_audio)
        }
        
        return (
            words_list,
            media_paths,
            str(instrumental_path), 
            str(actual_bg_visual) if actual_bg_visual else None,
            str(actual_audio),
            keep_vocals,
            use_original_video
        )
    except Exception as e:
        if isinstance(e, gr.Error):
            raise e
        raise gr.Error(f"Fehler: {str(e)}")

def start_rendering(regions_json, instrumental_path_str, bg_visual_str, audio_in_str, youtube_url_str, keep_vocals, use_original_video,
                   color_ungesungen, color_gesungen, font_size, lead_time, margin_v, use_entry_cues, downscale_1080p, progress=gr.Progress()):
    try:
        gr.Info("Timestamps übernommen! Starte Video-Rendering...")
        if not instrumental_path_str or not regions_json:
            raise gr.Error("Keine Extraktionsdaten gefunden. Bitte starte bei Schritt 1.")
            
        instrumental_path = Path(instrumental_path_str)
        bg_visual = Path(bg_visual_str) if bg_visual_str else None
        input_path = Path(audio_in_str)
        output_dir = Path("ergebnis_ui")
        
        config = VideokeConfig.load("configs/default.yaml")
        
        try:
            regions_data = json.loads(regions_json)
        except Exception:
            regions_data = []
            
        timestamps = []
        for r in regions_data:
            word = str(r.get("word", ""))
            start = float(r.get("start", 0))
            end = float(r.get("end", 0))
            timestamps.append(WordTimestamp(word=word, start=start, end=end, speaker=None))
            
        config.video.style.secondary_colour = hex_to_ass_color(color_ungesungen)
        config.video.style.primary_colour = hex_to_ass_color(color_gesungen)
        config.video.style.font_size = int(font_size)
        config.video.style.margin_v = int(margin_v)
        config.video.ass.lead_time_seconds = float(lead_time)
        config.video.ass.use_entry_cues = bool(use_entry_cues)
        config.video.downscale_1080p = bool(downscale_1080p)
        
        pipeline = VideokePipeline(config=config, input_path=input_path, output_dir=output_dir, bg_visual=bg_visual)
        
        final_results = None
        for status in pipeline.run_rendering(instrumental_path, timestamps, override_config=config, use_original_video=use_original_video):
            if isinstance(status, str):
                progress(0.8, desc=status)
            elif isinstance(status, dict):
                final_results = status
                
        if not final_results:
            raise gr.Error("Fehler beim Rendering.")
        gr.Info("Video erfolgreich gerendert!")
        return (
            str(final_results["video"]),
            gr.update(value=[str(final_results["video"]), str(final_results["instrumental"]), str(final_results["ass"])], visible=True)
        )
    except Exception as e:
        if isinstance(e, gr.Error):
            raise e
        raise gr.Error(f"Fehler: {str(e)}")

def export_wrapper(regions_json, media_paths, color_ungesungen, color_gesungen, font_size, lead_time, margin_v, use_entry_cues, downscale_1080p):
    try:
        gr.Info("Projekt-ZIP wird erstellt...")
        try:
            timestamps = json.loads(regions_json)
        except Exception:
            timestamps = []
            
        config_overrides = {
            "color_ungesungen": color_ungesungen,
            "color_gesungen": color_gesungen,
            "font_size": font_size,
            "lead_time": lead_time,
            "margin_v": margin_v,
            "use_entry_cues": use_entry_cues,
            "downscale_1080p": downscale_1080p
        }
        
        zip_path = export_project(timestamps, media_paths, config_overrides)
        gr.Info("Projekt bereit zum Download!")
        return str(zip_path)
    except Exception as e:
        if isinstance(e, gr.Error):
            raise e
        raise gr.Error(f"Fehler: {str(e)}")

def import_wrapper(zip_file):
    try:
        if not zip_file:
            raise gr.Error("Keine Datei hochgeladen.")
        media_paths, timestamps, config_overrides = import_project(zip_file.name)
        
        gr.Info("Projekt erfolgreich geladen!")
        return (
            media_paths,
            json.dumps(timestamps),
            config_overrides.get("color_ungesungen", "#FFFFFF"),
            config_overrides.get("color_gesungen", "#00FFFF"),
            config_overrides.get("font_size", 36),
            config_overrides.get("lead_time", 1.5),
            config_overrides.get("margin_v", 15),
            config_overrides.get("use_entry_cues", True),
            config_overrides.get("downscale_1080p", False),
            gr.update(value="Vocals")
        )
    except Exception as e:
        if isinstance(e, gr.Error):
            raise e
        raise gr.Error(f"Fehler: {str(e)}")

custom_css = """
.fullscreen-modal {
    position: fixed !important;
    top: 0; left: 0; width: 100vw; height: 100vh;
    background-color: rgba(17, 24, 39, 0.85);
    backdrop-filter: blur(8px);
    z-index: 9999 !important;
    display: flex !important;
    flex-direction: column; 
    justify-content: center; align-items: center;
}
.fullscreen-modal.hide, .fullscreen-modal.hidden, .fullscreen-modal[hidden] {
    display: none !important;
}
.modal-box {
    background: rgba(31, 41, 55, 0.9);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 40px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    text-align: center;
    max-width: 500px;
    width: 90%;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    animation: fadeIn 0.4s ease-out;
}
.modal-box h1 {
    font-size: 2rem;
    margin-bottom: 15px;
    background: linear-gradient(to right, #4facfe 0%, #00f2fe 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.modal-box p {
    font-size: 1.1rem;
    color: #cbd5e1;
    line-height: 1.5;
}
.pulse-icon {
    display: inline-block;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.1); }
    100% { transform: scale(1); }
}
@keyframes fadeIn {
    from { opacity: 0; transform: translate(-50%, -40%); }
    to { opacity: 1; transform: translate(-50%, -50%); }
}
"""

with gr.Blocks(theme=gr.themes.Soft(), css=custom_css) as demo:
    with gr.Column(visible=False, elem_classes=["fullscreen-modal"]) as loading_modal:
        gr.HTML("""
        <div class="modal-box">
            <h1><span class="pulse-icon">🚀</span> Analyse läuft...</h1>
            <p>Die KI trennt jetzt die Spuren und setzt die Timestamps.<br>Bitte einen Moment Geduld.</p>
        </div>
        """)
        
    gr.Markdown("# 🎤 Auto-Videoke Creator (Human-in-the-Loop)")
    
    state_instrumental = gr.State()
    state_bg_visual = gr.State()
    state_audio_in = gr.State()
    state_keep_vocals = gr.State()
    state_use_original_video = gr.State()
    
    with gr.Tabs(elem_id="main_tabs") as tabs:
        with gr.Tab("Schritt 1: Analyse", id="tab_analyse"):
            with gr.Row():
                with gr.Column(scale=1):
                    with gr.Tabs():
                        with gr.Tab("Lokale Datei"):
                            audio_in = gr.File(label="Song (MP3/WAV/MP4)", file_types=[".mp3", ".wav", ".flac", ".mp4", ".mov", ".mkv"])
                        with gr.Tab("YouTube Link"):
                            youtube_url = gr.Textbox(label="YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
                            
                    bg_in = gr.Image(type="filepath", label="Hintergrundbild (Optional)")
                    
                    keep_vocals_cb = gr.Checkbox(label="Nur Untertitel generieren, Original-Audio behalten", value=False)
                    use_original_video_cb = gr.Checkbox(label="Untertitel auf Original-Video legen", value=False)
                    
                    with gr.Accordion("Erweiterte Einstellungen (KI-Modelle)", open=False):
                        is_duet_cb = gr.Checkbox(label="Duett-Modus / Mehrere Sprecher (WhisperX Diarization)", value=False)
                        hf_token_input = gr.Textbox(type="password", label="Hugging Face Token", visible=False)
                        use_syllables_cb = gr.Checkbox(label="Experimentell: Silben-Splitting für flüssigeres Highlighting nutzen", value=False)
                    
                    is_duet_cb.change(fn=lambda x: gr.update(visible=x), inputs=[is_duet_cb], outputs=[hf_token_input])
                    
                    extract_btn = gr.Button("Analyse starten", variant="primary")
                    
        with gr.Tab("Schritt 2: Editor & Render", id="tab_editor"):
            with gr.Row():
                with gr.Column(scale=2):
                    gr.Markdown("### WhisperX Timestamps Editor")
                    with gr.Row():
                        btn_import = gr.File(label="Projekt laden (.zip)", file_types=[".zip", ".videoke"], type="filepath")
                        btn_export = gr.DownloadButton("Projekt speichern (.zip)")
                        
                    track_selector = gr.Radio(choices=["Vocals", "Instrumental", "Original"], value="Vocals", label="Audiospur wechseln")
                    gr.HTML('<div id="waveform-container" style="width: 100%; border: 1px solid #ccc; background: #1f2937; border-radius: 8px;"></div><div id="timeline-container"></div>')
                    
                    with gr.Row():
                        btn_play = gr.Button("▶ Play/Pause")
                        btn_zoom_in = gr.Button("➕ Zoom In")
                        btn_zoom_out = gr.Button("➖ Zoom Out")
                        btn_save = gr.Button("💾 Sync anwenden & Rendern", variant="primary", elem_id="btn_save_sync")
                        
                    slider_speed = gr.Slider(minimum=0.25, maximum=2.0, value=1.0, step=0.25, label="Wiedergabegeschwindigkeit (nur Vorschau)")
                        
                    media_paths_state = gr.JSON(visible=False)
                    words_state = gr.JSON(visible=False)
                    dummy_render_input = gr.Textbox(visible=False)
                    
                with gr.Column(scale=1):
                    gr.Markdown("### Visuelle Settings")
                    color_ungesungen = gr.ColorPicker(label="Standardfarbe (ungesungen)", value="#FFFFFF")
                    color_gesungen = gr.ColorPicker(label="Highlight-Farbe (gesungen)", value="#00FFFF")
                    font_size = gr.Slider(minimum=5, maximum=100, step=1, label="Schriftgröße", value=36)
                    lead_time = gr.Slider(minimum=0.0, maximum=3.0, step=0.1, label="Lead-Time (Sek.)", value=1.5)
                    use_entry_cues_cb = gr.Checkbox(label="Visual Countdowns vor Gesangseinsatz", value=True)
                    downscale_1080p_cb = gr.Checkbox(label="Video für schnelleres Rendering auf max. 1080p herunterskalieren (behält Seitenverhältnis)", value=False)
                    margin_v = gr.Slider(minimum=0, maximum=50, step=1, label="Abstand von unten (%)", value=15)
                    
            with gr.Row():
                with gr.Column():
                    video_out = gr.Video(label="Dein Karaoke-Video")
                    files_out = gr.File(label="Generierte Assets", visible=False, file_count="multiple")
            
    INIT_JS = """
    async (media_paths, words) => {
        if (!window.WaveSurfer) {
            const loadScript = (src) => new Promise(r => {
                const s = document.createElement('script');
                s.src = src;
                s.onload = r;
                document.head.appendChild(s);
            });
            await loadScript('https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js');
            await Promise.all([
                loadScript('https://unpkg.com/wavesurfer.js@7/dist/plugins/regions.min.js'),
                loadScript('https://unpkg.com/wavesurfer.js@7/dist/plugins/timeline.min.js')
            ]);
        }

        if (window.ws) {
            window.ws.destroy();
        }

        window.ws = WaveSurfer.create({
            container: '#waveform-container',
            waveColor: '#8b5cf6',
            progressColor: '#c4b5fd',
            minPxPerSec: 100,
            height: 128
        });

        const regionsPlugin = WaveSurfer.Regions.create();
        window.regionsPlugin = regionsPlugin;
        window.ws.registerPlugin(regionsPlugin);
        
        const timelinePlugin = WaveSurfer.Timeline.create({
            container: '#timeline-container',
        });
        window.ws.registerPlugin(timelinePlugin);
        
        if (media_paths && media_paths["Vocals"]) {
            window.ws.load('/file=' + media_paths["Vocals"]);
        }
        
        window.ws.once('decode', () => {
            if (words && words.length > 0) {
                words.forEach(w => {
                    const wordText = String(w.word || w.text || "");
                    regionsPlugin.addRegion({
                        start: w.start,
                        end: w.end,
                        content: wordText,
                        color: 'rgba(255, 255, 0, 0.4)',
                        drag: true,
                        resize: true
                    });
                });
            }
        });
        return [];
    }
    """

    IMPORT_JS = """
    async (media_paths, words_data, track) => {
        let words = [];
        try {
            words = typeof words_data === 'string' ? JSON.parse(words_data || "[]") : (words_data || []);
        } catch (e) {
            console.error("Error parsing words:", e);
        }
        
        if (!window.WaveSurfer) {
            const loadScript = (src) => new Promise(r => {
                const s = document.createElement('script');
                s.src = src;
                s.onload = r;
                document.head.appendChild(s);
            });
            await loadScript('https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js');
            await Promise.all([
                loadScript('https://unpkg.com/wavesurfer.js@7/dist/plugins/regions.min.js'),
                loadScript('https://unpkg.com/wavesurfer.js@7/dist/plugins/timeline.min.js')
            ]);
        }

        if (window.ws) {
            window.ws.destroy();
        }

        window.ws = WaveSurfer.create({
            container: '#waveform-container',
            waveColor: '#8b5cf6',
            progressColor: '#c4b5fd',
            minPxPerSec: 100,
            height: 128
        });

        const regionsPlugin = WaveSurfer.Regions.create();
        window.regionsPlugin = regionsPlugin;
        window.ws.registerPlugin(regionsPlugin);
        
        const timelinePlugin = WaveSurfer.Timeline.create({
            container: '#timeline-container',
        });
        window.ws.registerPlugin(timelinePlugin);
        
        if (media_paths && media_paths[track]) {
            window.ws.load('/file=' + media_paths[track]);
        }
        
        window.ws.once('decode', () => {
            if (words && words.length > 0) {
                words.forEach(w => {
                    const wordText = String(w.word || w.text || "");
                    regionsPlugin.addRegion({
                        start: w.start,
                        end: w.end,
                        content: wordText,
                        color: 'rgba(255, 255, 0, 0.4)',
                        drag: true,
                        resize: true
                    });
                });
            }
        });
        return [];
    }
    """

    extract_btn.click(
        fn=lambda: (gr.update(selected="tab_editor"), gr.update(visible=True)),
        inputs=None,
        outputs=[tabs, loading_modal]
    ).then(
        fn=start_extraction,
        inputs=[audio_in, bg_in, keep_vocals_cb, use_original_video_cb, is_duet_cb, hf_token_input, youtube_url, use_syllables_cb],
        outputs=[words_state, media_paths_state, state_instrumental, state_bg_visual, state_audio_in, state_keep_vocals, state_use_original_video]
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=None,
        outputs=[loading_modal]
    ).then(
        fn=None,
        inputs=[media_paths_state, words_state],
        js=INIT_JS
    )
    
    btn_play.click(fn=None, js="() => { if (window.ws) window.ws.playPause(); }")
    btn_zoom_in.click(fn=None, js="() => { if (window.ws) window.ws.zoom(window.ws.options.minPxPerSec * 1.5); }")
    btn_zoom_out.click(fn=None, js="() => { if (window.ws) window.ws.zoom(window.ws.options.minPxPerSec / 1.5); }")
    
    track_selector.change(
        fn=None,
        inputs=[track_selector, media_paths_state],
        js="""
        (track, media_paths) => {
            if (window.ws && window.regionsPlugin && media_paths && media_paths[track]) {
                const regions = window.regionsPlugin.getRegions().map(r => {
                    let textContent = "";
                    if (typeof r.content === 'string') {
                        textContent = r.content;
                    } else if (r.content instanceof HTMLElement) {
                        textContent = r.content.innerText || r.content.textContent;
                    } else if (r.element) {
                        textContent = r.element.innerText || r.element.textContent;
                    }
                    return {start: r.start, end: r.end, text: textContent, color: r.color};
                });
                
                window.ws.once('decode', () => {
                    window.regionsPlugin.clearRegions();
                    regions.forEach(r => {
                        const wordText = String(r.text || "");
                        window.regionsPlugin.addRegion({
                            start: r.start,
                            end: r.end,
                            content: wordText,
                            color: r.color,
                            drag: true,
                            resize: true
                        });
                    });
                });
                
                window.ws.load('/file=' + media_paths[track]);
            }
        }
        """
    )
    
    btn_save.click(
        fn=start_rendering,
        inputs=[
            dummy_render_input, state_instrumental, state_bg_visual, state_audio_in, youtube_url, state_keep_vocals, state_use_original_video,
            color_ungesungen, color_gesungen, font_size, lead_time, margin_v, use_entry_cues_cb, downscale_1080p_cb
        ],
        outputs=[video_out, files_out],
        js="""
        (dummy, inst, bg, aud, yt, keep, orig, sec, prim, fsize, lead, marg, cues, down) => {
            const btn = document.querySelector('#btn_save_sync');
            if(btn) {
                const oldText = btn.innerText;
                btn.innerText = "✅ Gespeichert!";
                setTimeout(() => { btn.innerText = oldText; }, 2000);
            }
            let data = [];
            if (window.regionsPlugin) {
                data = window.regionsPlugin.getRegions().map(r => {
                    let textContent = "";
                    if (typeof r.content === 'string') {
                        textContent = r.content;
                    } else if (r.content instanceof HTMLElement) {
                        textContent = r.content.innerText || r.content.textContent;
                    } else if (r.element) {
                        textContent = r.element.innerText || r.element.textContent;
                    }
                    return {word: textContent, start: r.start, end: r.end};
                });
            }
            return [JSON.stringify(data), inst, bg, aud, yt, keep, orig, sec, prim, fsize, lead, marg, cues, down];
        }
        """
    )
    
    btn_export.click(
        fn=export_wrapper,
        inputs=[dummy_render_input, media_paths_state, color_ungesungen, color_gesungen, font_size, lead_time, margin_v, use_entry_cues_cb, downscale_1080p_cb],
        outputs=[btn_export],
        js="""
        (dummy, media_paths, cu, cg, fsize, lead, marg, cues, down) => {
            let data = [];
            if (window.regionsPlugin) {
                data = window.regionsPlugin.getRegions().map(r => {
                    let textContent = "";
                    if (typeof r.content === 'string') {
                        textContent = r.content;
                    } else if (r.content instanceof HTMLElement) {
                        textContent = r.content.innerText || r.content.textContent;
                    } else if (r.element) {
                        textContent = r.element.innerText || r.element.textContent;
                    }
                    return {word: textContent, start: r.start, end: r.end};
                });
            }
            return [JSON.stringify(data), media_paths, cu, cg, fsize, lead, marg, cues, down];
        }
        """
    )

    btn_import.upload(
        fn=import_wrapper,
        inputs=[btn_import],
        outputs=[media_paths_state, words_state, color_ungesungen, color_gesungen, font_size, lead_time, margin_v, use_entry_cues_cb, downscale_1080p_cb, track_selector]
    ).then(
        fn=None,
        inputs=[media_paths_state, words_state, track_selector],
        js=IMPORT_JS
    )
    
    slider_speed.change(
        fn=None, 
        inputs=[slider_speed], 
        js="(speed) => { if (window.ws) { window.ws.setPlaybackRate(speed); } }"
    )


if __name__ == "__main__":
    import os
    allowed = str(Path("ergebnis_ui").absolute())
    demo.launch(server_name="0.0.0.0", share=False, allowed_paths=[allowed])
