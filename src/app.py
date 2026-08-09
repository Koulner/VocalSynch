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
from src.core.project_manager import export_project, import_project, sanitize_filename, list_projects
from src.text.translator import translate_regions

def hex_to_ass_color(hex_rgb: str) -> str:
    """Konvertiert Gradio RGB Hex (#RRGGBB) zu ASS BGR Hex (&H00BBGGRR)."""
    hex_rgb = hex_rgb.lstrip('#')
    if len(hex_rgb) == 6:
        r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"

def start_extraction(audio_input, bg_input, keep_vocals, use_original_video, is_duet, hf_token, use_syllables, progress=gr.Progress()):
    try:
        if not audio_input:
            raise gr.Error("Bitte lade eine Audio- oder Videodatei hoch.")
            
        output_dir = Path("ergebnis_ui")
        output_dir.mkdir(parents=True, exist_ok=True)
        
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
            
        words_list = []
        current_char_count = 0
        for i, wt in enumerate(timestamps):
            word_text = str(wt.word).strip()
            is_break = False
            
            if i == 0:
                is_break = True
            else:
                prev_wt = timestamps[i-1]
                gap = wt.start - prev_wt.end
                if gap > 0.8:
                    is_break = True
                elif any(punct in str(prev_wt.word) for punct in ['.', '?', '!']):
                    is_break = True
                elif current_char_count > 30:
                    is_break = True
                    
            if is_break:
                current_char_count = len(word_text)
            else:
                current_char_count += len(word_text) + 1
                
            words_list.append({
                "word": wt.word,
                "start": wt.start,
                "end": wt.end,
                "speaker": wt.speaker or "",
                "line_break": is_break
            })
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

def start_rendering(regions_json, instrumental_path_str, bg_visual_str, audio_in_str, keep_vocals, use_original_video,
                   color_ungesungen, color_gesungen, font_size, lead_time, pos_x, pos_y, use_entry_cues, downscale_1080p, project_name, animation_style, progress=gr.Progress()):
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
            is_line = bool(r.get("line_break", False))
            is_block = bool(r.get("block_break", False))
            timestamps.append(WordTimestamp(word=word, start=start, end=end, speaker=None, line_break=is_line, block_break=is_block))
            
        config.video.style.secondary_colour = hex_to_ass_color(color_ungesungen)
        config.video.style.primary_colour = hex_to_ass_color(color_gesungen)
        config.video.style.font_size = int(font_size)
        config.video.style.pos_x = float(pos_x)
        config.video.style.pos_y = float(pos_y)
        config.video.ass.lead_time_seconds = float(lead_time)
        config.video.ass.use_entry_cues = bool(use_entry_cues)
        config.video.ass.animation_style = animation_style
        config.video.downscale_1080p = bool(downscale_1080p)
        
        pipeline = VideokePipeline(config=config, input_path=input_path, output_dir=output_dir, bg_visual=bg_visual)
        
        final_results = None
        for status in pipeline.run_rendering(instrumental_path, timestamps, override_config=config, use_original_video=use_original_video, project_name=project_name):
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

def export_wrapper(regions_json, media_paths, color_ungesungen, color_gesungen, font_size, lead_time, pos_x, pos_y, use_entry_cues, downscale_1080p, project_name, old_project_path, animation_style):
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
            "pos_x": pos_x,
            "pos_y": pos_y,
            "use_entry_cues": use_entry_cues,
            "downscale_1080p": downscale_1080p,
            "animation_style": animation_style
        }
        
        zip_path = export_project(timestamps, media_paths, config_overrides, project_name=project_name, old_project_path=old_project_path)
        gr.Info("Projekt gespeichert!")
        return str(zip_path), gr.update(value=list_projects())
    except Exception as e:
        if isinstance(e, gr.Error):
            raise e
        raise gr.Error(f"Fehler: {str(e)}")

def import_wrapper(zip_file):
    try:
        if not zip_file:
            raise gr.Error("Keine Datei hochgeladen oder ausgewählt.")
        file_path = zip_file.name if hasattr(zip_file, "name") else str(zip_file)
        media_paths, timestamps, config_overrides, project_name = import_project(file_path)
        
        gr.Info("Projekt erfolgreich geladen!")
        return (
            media_paths,
            json.dumps(timestamps),
            config_overrides.get("color_ungesungen", "#FFFFFF"),
            config_overrides.get("color_gesungen", "#00FFFF"),
            config_overrides.get("font_size", 35),
            config_overrides.get("lead_time", 1.5),
            config_overrides.get("pos_x", 50),
            config_overrides.get("pos_y", 80),
            config_overrides.get("use_entry_cues", True),
            config_overrides.get("downscale_1080p", False),
            gr.update(value="Vocals"),
            gr.update(value=project_name),
            media_paths.get("Instrumental"),
            None,
            media_paths.get("Original"),
            False,
            False,
            file_path
        )
    except Exception as e:
        if isinstance(e, gr.Error):
            raise e
        raise gr.Error(f"Fehler: {str(e)}")

custom_css = """
#preview-monitor {
    width: 100%; aspect-ratio: 16/9; max-height: 400px;
    background-color: #0f172a; /* Schiefergrau dunkel */
    border: 2px solid #1e293b; border-radius: 8px;
    display: flex; justify-content: center; align-items: center;
    overflow: hidden; position: relative; margin-bottom: 16px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
}
#preview-text-container {
    text-align: center; color: white; font-size: 2.5rem;
    font-family: 'Segoe UI', sans-serif; font-weight: bold;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.8);
}
.preview-word { display: inline-block; margin: 0 6px; transition: transform 0.1s ease; }
/* Styles für das aktive Wort */
.word-active-karaoke { color: #10b981; } /* Smaragdgrün */
.word-active-popup { color: #10b981; transform: scale(1.25); }
.word-selected { border-bottom: 3px solid #3b82f6; padding-bottom: 2px; }

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

with gr.Blocks(theme=gr.themes.Base(primary_hue=gr.themes.colors.emerald), css=custom_css) as demo:
    with gr.Column(visible=False, elem_classes=["fullscreen-modal"]) as loading_modal:
        gr.HTML("""
        <div class="modal-box">
            <h1><span class="pulse-icon">🚀</span> Analyse läuft...</h1>
            <p>Die KI trennt jetzt die Spuren und setzt die Timestamps.<br>Bitte einen Moment Geduld.</p>
        </div>
        """)
        
    gr.Markdown("# 🎤 VocalSync Pro (Human-in-the-Loop)")
    
    state_instrumental = gr.State()
    state_bg_visual = gr.State()
    state_audio_in = gr.State()
    state_keep_vocals = gr.State()
    state_use_original_video = gr.State()
    current_project_path = gr.State(value=None)
    
    with gr.Tabs(elem_id="main_tabs") as tabs:
        with gr.Tab("🏠 Startseite / Projekte", id="tab_home"):
            gr.Markdown("# 🎤 Willkommen in VocalSync Pro")
            with gr.Row():
                btn_new_project = gr.Button("✨ Neues Projekt starten", variant="primary", size="lg")
                upload_import_hub = gr.File(label="📁 Projekt importieren (.zip)", file_types=[".zip", ".videoke"])
                btn_refresh_hub = gr.Button("🔄 Liste aktualisieren")
            
            gr.Markdown("### 📂 Zuletzt bearbeitete Projekte")
            table_projects = gr.Dataframe(
                headers=["Projektname", "Zuletzt bearbeitet", "Pfad"], 
                interactive=False, 
                type="array"
            )
            selected_project_path = gr.State(value=None)
            btn_delete_project = gr.Button("🗑️ Ausgewähltes Projekt löschen", variant="stop")

        with gr.Tab("Schritt 1: Analyse", id="tab_analyse"):
            with gr.Row():
                with gr.Column(scale=1):
                    audio_in = gr.File(label="Song (MP3/WAV/MP4)", file_types=[".mp3", ".wav", ".flac", ".mp4", ".mov", ".mkv"])
                            
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
                    input_project_name = gr.Textbox(label="Projektname", value="Neues_Projekt", max_lines=1)
                    with gr.Row():
                        btn_save_project = gr.Button("💾 Speichern", variant="primary")
                        btn_save_as_project = gr.Button("📁 Speichern unter (Duplizieren)")
                        
                    track_selector = gr.Radio(choices=["Vocals", "Instrumental", "Original"], value="Vocals", label="Audiospur wechseln")
                    gr.HTML('<div id="preview-monitor"><div id="preview-text-container"></div></div>')
                    gr.HTML('<div id="waveform-container" style="width: 100%; border: 1px solid #ccc; background: #1f2937; border-radius: 8px;"></div><div id="timeline-container"></div>')
                    with gr.Accordion("ℹ️ Editor Shortcuts & Hilfe", open=False):
                        gr.Markdown("""
                        * **Doppelklick:** Wort bearbeiten
                        * **[Entf] / [Backspace]:** Wort löschen
                        * **[Tab] / [Shift+Tab]:** Zum nächsten/vorherigen Textblock springen
                        * **[Pfeil Links] / [Pfeil Rechts]:** 0.2s vor/zurück spulen
                        * **[Enter]:** Neuen Textblock beginnen (Wort wird Blau)
                        * **[Shift] + [Enter]:** Zeilenumbruch im selben Block einfügen (Wort wird Orange)
                        * **[Strg] + [Z] / [Y]:** Rückgängig / Wiederholen
                        """)
                    
                    with gr.Row():
                        btn_play = gr.Button("▶ Play/Pause")
                        btn_zoom_in = gr.Button("➕ Zoom In")
                        btn_zoom_out = gr.Button("➖ Zoom Out")
                        btn_auto_chunking = gr.Button("🔄 Auto-Umbruch")
                        btn_save = gr.Button("💾 Sync anwenden & Rendern", variant="primary", elem_id="btn_save_sync")
                        
                    with gr.Row():
                        dropdown_target_lang = gr.Dropdown(choices=["en", "de", "es", "fr", "it", "pt", "nl"], value="en", label="🌐 Sprache übersetzen")
                        btn_translate = gr.Button("Übersetzen & Anwenden")
                        
                    slider_speed = gr.Slider(minimum=0.25, maximum=2.0, value=1.0, step=0.25, label="Wiedergabegeschwindigkeit (nur Vorschau)")
                        
                    media_paths_state = gr.JSON(visible=False)
                    words_state = gr.JSON(visible=False)
                    dummy_render_input = gr.Textbox(visible=False)
                    
                with gr.Column(scale=1):
                    gr.Markdown("### Visuelle Settings")
                    dropdown_anim_style = gr.Dropdown(choices=["Standard", "Karaoke Fill", "TikTok Pop-Up", "Typewriter"], value="TikTok Pop-Up", label="Animations-Stil")
                    color_ungesungen = gr.ColorPicker(label="Standardfarbe (ungesungen)", value="#FFFFFF")
                    color_gesungen = gr.ColorPicker(label="Highlight-Farbe (gesungen)", value="#00FFFF")
                    font_size = gr.Slider(minimum=5, maximum=100, step=1, label="Schriftgröße (px)", value=35)
                    pos_x = gr.Slider(minimum=0, maximum=100, step=1, label="Position X (%)", value=50)
                    pos_y = gr.Slider(minimum=0, maximum=100, step=1, label="Position Y (%)", value=80)
                    lead_time = gr.Slider(minimum=0.0, maximum=3.0, step=0.1, label="Lead-Time (Sek.)", value=1.5)
                    use_entry_cues_cb = gr.Checkbox(label="Visual Countdowns vor Gesangseinsatz", value=True)
                    downscale_1080p_cb = gr.Checkbox(label="Video für schnelleres Rendering auf max. 1080p herunterskalieren (behält Seitenverhältnis)", value=False)
                    
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
            waveColor: '#475569',
            progressColor: '#10b981',
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
        
        window.historyStack = [];
        window.historyIndex = -1;
        window.isRestoring = false;

        window.saveState = function() {
            if (window.isRestoring) return;
            const currentState = regionsPlugin.getRegions().map(r => {
                let text = "";
                if (typeof r.content === 'string') text = r.content;
                else if (r.element) text = r.element.innerText || r.element.textContent;
                return { start: r.start, end: r.end, content: text, color: r.color };
            });
            window.historyStack = window.historyStack.slice(0, window.historyIndex + 1);
            window.historyStack.push(currentState);
            window.historyIndex++;
        };

        window.loadState = function(index) {
            if (index < 0 || index >= window.historyStack.length) return;
            window.isRestoring = true;
            regionsPlugin.clearRegions();
            const state = window.historyStack[index];
            state.forEach(item => {
                regionsPlugin.addRegion({
                    start: item.start,
                    end: item.end,
                    content: item.content,
                    color: item.color || 'rgba(16, 185, 129, 0.3)',
                    drag: true,
                    resize: true
                });
            });
            window.historyIndex = index;
            setTimeout(() => { window.isRestoring = false; }, 50);
        };

        regionsPlugin.enableDragSelection({
            color: 'rgba(255, 255, 0, 0.4)'
        });

        regionsPlugin.on('region-created', (region) => {
            if (region.content) return;
            const newText = prompt("Neues Wort für diesen Bereich eingeben:");
            if (newText !== null && newText.trim() !== "") {
                region.setOptions({ content: newText.trim(), drag: true, resize: true });
                window.saveState();
            } else {
                region.remove();
            }
        });

        window.activeRegion = null;
        regionsPlugin.on('region-clicked', (region, e) => {
            e.stopPropagation();
            window.activeRegion = region;
            if (window.updatePreviewMonitor) window.updatePreviewMonitor();
        });

        if (!window.ws_keydown_listener) {
            window.ws_keydown_listener = (e) => {
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                
                // TAB: Springe zum nächsten/vorherigen blauen Block
                if (e.key === 'Tab') {
                    e.preventDefault();
                    if (!window.ws || !window.ws.plugins[0]) return;
                    const time = window.ws.getCurrentTime();
                    const regions = window.ws.plugins[0].getRegions().sort((a,b) => parseFloat(a.start) - parseFloat(b.start));
                    
                    let targetBreak = null;
                    if (e.shiftKey) { // Shift+Tab (Zurück)
                        let breaks = regions.filter(r => parseFloat(r.start) < time - 0.2 && (r.data?.isLineBreak || r.customLineBreak || (String(r.color).replace(/\s/g, '').toLowerCase().includes('59,130,246'))));
                        if (breaks.length > 0) targetBreak = breaks[breaks.length - 1];
                    } else { // Tab (Vor)
                        targetBreak = regions.find(r => parseFloat(r.start) > time + 0.2 && (r.data?.isLineBreak || r.customLineBreak || (String(r.color).replace(/\s/g, '').toLowerCase().includes('59,130,246'))));
                    }
                    
                    if (targetBreak) {
                        window.ws.setTime(targetBreak.start);
                        window.activeRegion = targetBreak; 
                        if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                    }
                }
                
                // PFEILTASTEN: Spulen
                if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    if(window.ws) { window.ws.setTime(Math.min(window.ws.getDuration(), window.ws.getCurrentTime() + 0.2)); }
                    if(window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    if(window.ws) { window.ws.setTime(Math.max(0, window.ws.getCurrentTime() - 0.2)); }
                    if(window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                
                if (e.ctrlKey || e.metaKey) {
                    if (e.key.toLowerCase() === 'z') {
                        e.preventDefault();
                        if (e.shiftKey) {
                            window.loadState(window.historyIndex + 1);
                        } else {
                            window.loadState(window.historyIndex - 1);
                        }
                    } else if (e.key.toLowerCase() === 'y') {
                        e.preventDefault();
                        window.loadState(window.historyIndex + 1);
                    }
                }
                
                if ((e.key === 'Backspace' || e.key === 'Delete') && window.activeRegion) {
                    window.activeRegion.remove();
                    window.activeRegion = null;
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                
                // SHIFT + ENTER: Zeilenumbruch (Orange)
                if (e.key === 'Enter' && e.shiftKey && window.activeRegion) {
                    e.preventDefault();
                    let isLine = !(window.activeRegion.data?.isLineBreak || false);
                    window.activeRegion.data = { isBlockBreak: false, isLineBreak: isLine };
                    window.activeRegion.setOptions({ 
                        color: isLine ? 'rgba(245, 158, 11, 0.5)' : 'rgba(16, 185, 129, 0.4)', 
                        data: window.activeRegion.data 
                    });
                    window.saveState(); 
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                // NUR ENTER: Neuer Block (Blau)
                else if (e.key === 'Enter' && !e.shiftKey && window.activeRegion) {
                    e.preventDefault();
                    let isBlock = !(window.activeRegion.data?.isBlockBreak || false);
                    window.activeRegion.data = { isBlockBreak: isBlock, isLineBreak: false };
                    window.activeRegion.setOptions({ 
                        color: isBlock ? 'rgba(59, 130, 246, 0.5)' : 'rgba(16, 185, 129, 0.4)', 
                        data: window.activeRegion.data 
                    });
                    window.saveState(); 
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
            };
            document.addEventListener('keydown', window.ws_keydown_listener);
        }

        window.regionsPlugin.on('region-double-clicked', (region, e) => {
            e.stopPropagation();
            let currentText = "";
            if (typeof region.content === 'string') {
                currentText = region.content;
            } else if (region.element) {
                currentText = region.element.innerText || region.element.textContent;
            }
            const newText = prompt("Wort korrigieren:", currentText);
            if (newText !== null && newText.trim() !== "") {
                region.setOptions({ content: newText.trim() });
                window.saveState();
            }
        });
        
        regionsPlugin.on('region-update-end', window.saveState);
        regionsPlugin.on('region-removed', window.saveState);

        window.ws.once('decode', () => {
            if (words && words.length > 0) {
                words.forEach((item, idx) => {
                    let isBlock = item.block_break || false;
                    let isLine = item.line_break || false;
                    
                    // LEGACY SUPPORT: Alte Projekte hatten nur 'line_break' als blauen Block-Umbruch.
                    if (item.line_break === true && item.block_break === undefined) {
                        isBlock = true;
                        isLine = false;
                    }
                    if (idx === 0) isBlock = true;

                    let rColor = 'rgba(16, 185, 129, 0.4)'; // Gruen
                    if (isBlock) rColor = 'rgba(59, 130, 246, 0.5)'; // Blau
                    else if (isLine) rColor = 'rgba(245, 158, 11, 0.5)'; // Orange

                    regionsPlugin.addRegion({
                        start: item.start,
                        end: item.end,
                        content: String(item.word || item.text || ""),
                        color: rColor,
                        data: { isBlockBreak: isBlock, isLineBreak: isLine },
                        drag: true,
                        resize: true
                    });
                });
                
                const hasSavedBreaks = words.filter((item, index) => index > 0 && (item.block_break || item.line_break || (item.line_break && item.block_break === undefined))).length > 0;
                if (!hasSavedBreaks && window.applyAutoChunking) {
                    setTimeout(() => window.applyAutoChunking(), 500);
                } else {
                    setTimeout(() => {
                        window.saveState();
                        if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                    }, 500);
                }
            }
        });
        
        window.applyAutoChunking = function() {
            if (!window.ws || !window.ws.plugins[0]) return;
            const regions = window.ws.plugins[0].getRegions().sort((a,b) => parseFloat(a.start) - parseFloat(b.start));
            let charCount = 0;
            
            regions.forEach((r, i) => {
                let isBreak = false;
                let text = typeof r.content === 'string' ? r.content : (r.element ? r.element.innerText || r.element.textContent : "");
                let textLen = text.length;
                
                if (i === 0) {
                    isBreak = true;
                    charCount = textLen;
                } else {
                    let prev = regions[i-1];
                    let gap = parseFloat(r.start) - parseFloat(prev.end);
                    if (gap > 0.8 || (charCount + textLen) > 35) {
                        isBreak = true;
                        charCount = textLen;
                    } else {
                        charCount += (textLen + 1);
                    }
                }
                
                r.data = { isBlockBreak: isBreak, isLineBreak: false };
                r.setOptions({ color: isBreak ? 'rgba(59, 130, 246, 0.5)' : 'rgba(16, 185, 129, 0.4)', data: r.data });
            });
            
            window.saveState();
            if (window.updatePreviewMonitor) window.updatePreviewMonitor();
        };
        // ==========================================
        // Live Preview Monitor Sync Engine
        // ==========================================
        window.onPreviewWordClick = function(regionId) {
            if (!window.regionsPlugin) return;
            const regions = window.regionsPlugin.getRegions();
            const r = regions.find(x => x.id === regionId);
            if (r) {
                window.activeRegion = r;
                window.ws.setTime(r.start);
                if (window.updatePreviewMonitor) window.updatePreviewMonitor();
            }
        };

        window.onPreviewWordDblClick = function(regionId) {
            if (!window.regionsPlugin) return;
            const regions = window.regionsPlugin.getRegions();
            const r = regions.find(x => x.id === regionId);
            if (r) {
                let currentText = typeof r.content === 'string' ? r.content : (r.element ? r.element.innerText || r.element.textContent : "");
                const newText = prompt("Wort korrigieren:", currentText);
                if (newText !== null && newText.trim() !== "") {
                    r.setOptions({ content: newText.trim() });
                    window.saveState();
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
            }
        };

        window.updatePreviewMonitor = function() {
            if (!window.ws || !window.regionsPlugin) return;
            const time = window.ws.getCurrentTime();
            const monitor = document.getElementById('preview-text-container');
            if (!monitor) return;

            const regions = window.regionsPlugin.getRegions().sort((a, b) => parseFloat(a.start) - parseFloat(b.start));
            
            let lines = [];
            let currentLine = [];
            
            // 1. BULLETPROOF CHUNKING (Farberkennung)
            regions.forEach(r => {
                const colorStr = String(r.color || "").replace(/\s/g, '').toLowerCase();
                const isBlue = colorStr.includes('59,130,246') || colorStr.includes('#3b82f6');
                const isBlock = r.data?.isBlockBreak || isBlue;
                
                if (isBlock || currentLine.length === 0) {
                    if (currentLine.length > 0) lines.push(currentLine);
                    currentLine = [r];
                } else {
                    currentLine.push(r);
                }
            });
            if (currentLine.length > 0) lines.push(currentLine);

            // 2. EXAKTE ZEITFENSTER BERECHNEN (Keine Überlappungen!)
            let activeLine = null;
            for (let i = 0; i < lines.length; i++) {
                let line = lines[i];
                if (line.length === 0) continue;
                let lineStart = parseFloat(line[0].start);
                
                // Die Anzeigedauer einer Zeile endet EXAKT, wenn die nächste beginnt.
                let lineEnd = (i < lines.length - 1) ? parseFloat(lines[i+1][0].start) : parseFloat(line[line.length - 1].end) + 0.5;
                
                if (time >= lineStart && time < lineEnd) {
                    activeLine = line;
                    break;
                }
            }

            // 3. RENDER HTML
            if (activeLine) {
                let html = "";
                activeLine.forEach((r, idx) => {
                    let text = typeof r.content === 'string' ? r.content : (r.element ? r.element.innerText || r.element.textContent : "");
                    let start = parseFloat(r.start);
                    let end = parseFloat(r.end);
                    
                    let isLineBreak = r.data?.isLineBreak || (String(r.color || "").replace(/\s/g, '').toLowerCase().includes('245,158,11'));
                    if (isLineBreak) html += `<br>`;
                    
                    let cssClass = "preview-word";
                    
                    if (time >= start && time <= end) {
                        if (time <= start + 0.15) {
                            cssClass += " word-active-popup";
                        } else {
                            cssClass += " word-active-karaoke";
                        }
                    } else if (time > end) {
                        cssClass += " word-active-karaoke";
                    }
                    
                    let isSelected = (window.activeRegion && window.activeRegion.id === r.id);
                    if (isSelected) cssClass += " word-selected";
                    
                    html += `<span class="${cssClass}" 
                                style="cursor:pointer;" 
                                onclick="window.onPreviewWordClick('${r.id}')" 
                                ondblclick="window.onPreviewWordDblClick('${r.id}')">
                                ${text}
                             </span>`;
                });
                
                if (monitor.innerHTML !== html) monitor.innerHTML = html;
            } else {
                if (monitor.innerHTML !== "") monitor.innerHTML = "";
            }
        };

        // 60 FPS requestAnimationFrame Loop für absolut flüssige Sync während der Wiedergabe
        if (window.previewRafId) cancelAnimationFrame(window.previewRafId);
        const loopPreview = () => {
            if (window.ws && window.ws.isPlaying()) {
                window.updatePreviewMonitor();
            }
            window.previewRafId = requestAnimationFrame(loopPreview);
        };
        loopPreview();

        // Fallback für Klicks und Drags im pausierten Zustand
        ['seek', 'seeking', 'timeupdate'].forEach(evt => {
            window.ws.on(evt, window.updatePreviewMonitor);
        });
        window.regionsPlugin.on('region-update-end', window.updatePreviewMonitor);
        
        // Initiales Update beim Laden
        setTimeout(window.updatePreviewMonitor, 100);

        const dragMonitor = document.getElementById('preview-monitor');
        const dragContainer = document.getElementById('preview-text-container');
        dragContainer.style.position = 'absolute';
        if (!dragContainer.style.left) dragContainer.style.left = '50%';
        if (!dragContainer.style.top) dragContainer.style.top = '80%';
        dragContainer.style.transform = 'translate(-50%, -100%)';
        dragContainer.style.width = 'max-content';
        dragContainer.style.cursor = 'move';
        
        if (!window.dragControllerInit) {
            window.dragControllerInit = true;
            window.dragController = {
                isDragging: false,
                down: function(e) {
                    if (e.target.tagName !== 'SPAN') window.dragController.isDragging = true;
                },
                move: function(e) {
                    if (!window.dragController.isDragging) return;
                    const rect = dragMonitor.getBoundingClientRect();
                    let x = e.clientX - rect.left;
                    let y = e.clientY - rect.top;
                    let px = (x / rect.width) * 100;
                    let py = (y / rect.height) * 100;
                    px = Math.max(0, Math.min(100, px));
                    py = Math.max(0, Math.min(100, py));
                    dragContainer.style.left = px + '%';
                    dragContainer.style.top = py + '%';
                },
                up: function(e) { window.dragController.isDragging = false; }
            };
            dragMonitor.addEventListener('mousedown', window.dragController.down);
            document.addEventListener('mousemove', window.dragController.move);
            document.addEventListener('mouseup', window.dragController.up);
        }
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
            waveColor: '#475569',
            progressColor: '#10b981',
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
        
        window.historyStack = [];
        window.historyIndex = -1;
        window.isRestoring = false;

        window.saveState = function() {
            if (window.isRestoring) return;
            const currentState = regionsPlugin.getRegions().map(r => {
                let text = "";
                if (typeof r.content === 'string') text = r.content;
                else if (r.element) text = r.element.innerText || r.element.textContent;
                return { start: r.start, end: r.end, content: text, color: r.color };
            });
            window.historyStack = window.historyStack.slice(0, window.historyIndex + 1);
            window.historyStack.push(currentState);
            window.historyIndex++;
        };

        window.loadState = function(index) {
            if (index < 0 || index >= window.historyStack.length) return;
            window.isRestoring = true;
            regionsPlugin.clearRegions();
            const state = window.historyStack[index];
            state.forEach(item => {
                regionsPlugin.addRegion({
                    start: item.start,
                    end: item.end,
                    content: item.content,
                    color: item.color || 'rgba(16, 185, 129, 0.3)',
                    drag: true,
                    resize: true
                });
            });
            window.historyIndex = index;
            setTimeout(() => { window.isRestoring = false; }, 50);
        };

        regionsPlugin.enableDragSelection({
            color: 'rgba(255, 255, 0, 0.4)'
        });

        regionsPlugin.on('region-created', (region) => {
            if (region.content) return;
            const newText = prompt("Neues Wort für diesen Bereich eingeben:");
            if (newText !== null && newText.trim() !== "") {
                region.setOptions({ content: newText.trim(), drag: true, resize: true });
                window.saveState();
            } else {
                region.remove();
            }
        });

        window.activeRegion = null;
        regionsPlugin.on('region-clicked', (region, e) => {
            e.stopPropagation();
            window.activeRegion = region;
            if (window.updatePreviewMonitor) window.updatePreviewMonitor();
        });

        if (!window.ws_keydown_listener) {
            window.ws_keydown_listener = (e) => {
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                
                // TAB: Springe zum nächsten/vorherigen blauen Block
                if (e.key === 'Tab') {
                    e.preventDefault();
                    if (!window.ws || !window.ws.plugins[0]) return;
                    const time = window.ws.getCurrentTime();
                    const regions = window.ws.plugins[0].getRegions().sort((a,b) => parseFloat(a.start) - parseFloat(b.start));
                    
                    let targetBreak = null;
                    if (e.shiftKey) { // Shift+Tab (Zurück)
                        let breaks = regions.filter(r => parseFloat(r.start) < time - 0.2 && (r.data?.isLineBreak || r.customLineBreak || (String(r.color).replace(/\s/g, '').toLowerCase().includes('59,130,246'))));
                        if (breaks.length > 0) targetBreak = breaks[breaks.length - 1];
                    } else { // Tab (Vor)
                        targetBreak = regions.find(r => parseFloat(r.start) > time + 0.2 && (r.data?.isLineBreak || r.customLineBreak || (String(r.color).replace(/\s/g, '').toLowerCase().includes('59,130,246'))));
                    }
                    
                    if (targetBreak) {
                        window.ws.setTime(targetBreak.start);
                        window.activeRegion = targetBreak; 
                        if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                    }
                }
                
                // PFEILTASTEN: Spulen
                if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    if(window.ws) { window.ws.setTime(Math.min(window.ws.getDuration(), window.ws.getCurrentTime() + 0.2)); }
                    if(window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    if(window.ws) { window.ws.setTime(Math.max(0, window.ws.getCurrentTime() - 0.2)); }
                    if(window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                
                if (e.ctrlKey || e.metaKey) {
                    if (e.key.toLowerCase() === 'z') {
                        e.preventDefault();
                        if (e.shiftKey) {
                            window.loadState(window.historyIndex + 1);
                        } else {
                            window.loadState(window.historyIndex - 1);
                        }
                    } else if (e.key.toLowerCase() === 'y') {
                        e.preventDefault();
                        window.loadState(window.historyIndex + 1);
                    }
                }
                
                if ((e.key === 'Backspace' || e.key === 'Delete') && window.activeRegion) {
                    window.activeRegion.remove();
                    window.activeRegion = null;
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                
                // SHIFT + ENTER: Zeilenumbruch (Orange)
                if (e.key === 'Enter' && e.shiftKey && window.activeRegion) {
                    e.preventDefault();
                    let isLine = !(window.activeRegion.data?.isLineBreak || false);
                    window.activeRegion.data = { isBlockBreak: false, isLineBreak: isLine };
                    window.activeRegion.setOptions({ 
                        color: isLine ? 'rgba(245, 158, 11, 0.5)' : 'rgba(16, 185, 129, 0.4)', 
                        data: window.activeRegion.data 
                    });
                    window.saveState(); 
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
                // NUR ENTER: Neuer Block (Blau)
                else if (e.key === 'Enter' && !e.shiftKey && window.activeRegion) {
                    e.preventDefault();
                    let isBlock = !(window.activeRegion.data?.isBlockBreak || false);
                    window.activeRegion.data = { isBlockBreak: isBlock, isLineBreak: false };
                    window.activeRegion.setOptions({ 
                        color: isBlock ? 'rgba(59, 130, 246, 0.5)' : 'rgba(16, 185, 129, 0.4)', 
                        data: window.activeRegion.data 
                    });
                    window.saveState(); 
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
            };
            document.addEventListener('keydown', window.ws_keydown_listener);
        }

        window.regionsPlugin.on('region-double-clicked', (region, e) => {
            e.stopPropagation();
            let currentText = "";
            if (typeof region.content === 'string') {
                currentText = region.content;
            } else if (region.element) {
                currentText = region.element.innerText || region.element.textContent;
            }
            const newText = prompt("Wort korrigieren:", currentText);
            if (newText !== null && newText.trim() !== "") {
                region.setOptions({ content: newText.trim() });
                window.saveState();
                if (window.updatePreviewMonitor) window.updatePreviewMonitor();
            }
        });
        
        regionsPlugin.on('region-update-end', window.saveState);
        regionsPlugin.on('region-removed', window.saveState);

        window.ws.once('decode', () => {
            if (words && words.length > 0) {
                words.forEach((item, idx) => {
                    let isBlock = item.block_break || false;
                    let isLine = item.line_break || false;
                    
                    // LEGACY SUPPORT: Alte Projekte hatten nur 'line_break' als blauen Block-Umbruch.
                    if (item.line_break === true && item.block_break === undefined) {
                        isBlock = true;
                        isLine = false;
                    }
                    if (idx === 0) isBlock = true;

                    let rColor = 'rgba(16, 185, 129, 0.4)'; // Gruen
                    if (isBlock) rColor = 'rgba(59, 130, 246, 0.5)'; // Blau
                    else if (isLine) rColor = 'rgba(245, 158, 11, 0.5)'; // Orange

                    regionsPlugin.addRegion({
                        start: item.start,
                        end: item.end,
                        content: String(item.word || item.text || ""),
                        color: rColor,
                        data: { isBlockBreak: isBlock, isLineBreak: isLine },
                        drag: true,
                        resize: true
                    });
                });
                
                const hasSavedBreaks = words.filter((item, index) => index > 0 && (item.block_break || item.line_break || (item.line_break && item.block_break === undefined))).length > 0;
                if (!hasSavedBreaks && window.applyAutoChunking) {
                    setTimeout(() => window.applyAutoChunking(), 500);
                } else {
                    setTimeout(() => {
                        window.saveState();
                        if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                    }, 500);
                }
            }
        });

        window.applyAutoChunking = function() {
            if (!window.ws || !window.ws.plugins[0]) return;
            const regions = window.ws.plugins[0].getRegions().sort((a,b) => parseFloat(a.start) - parseFloat(b.start));
            let charCount = 0;
            
            regions.forEach((r, i) => {
                let isBreak = false;
                let text = typeof r.content === 'string' ? r.content : (r.element ? r.element.innerText || r.element.textContent : "");
                let textLen = text.length;
                
                if (i === 0) {
                    isBreak = true;
                    charCount = textLen;
                } else {
                    let prev = regions[i-1];
                    let gap = parseFloat(r.start) - parseFloat(prev.end);
                    if (gap > 0.8 || (charCount + textLen) > 35) {
                        isBreak = true;
                        charCount = textLen;
                    } else {
                        charCount += (textLen + 1);
                    }
                }
                
                r.data = { isBlockBreak: isBreak, isLineBreak: false };
                r.setOptions({ color: isBreak ? 'rgba(59, 130, 246, 0.5)' : 'rgba(16, 185, 129, 0.4)', data: r.data });
            });
            
            window.saveState();
            if (window.updatePreviewMonitor) window.updatePreviewMonitor();
        };
        // ==========================================
        // Live Preview Monitor Sync Engine
        // ==========================================
        window.onPreviewWordClick = function(regionId) {
            if (!window.regionsPlugin) return;
            const regions = window.regionsPlugin.getRegions();
            const r = regions.find(x => x.id === regionId);
            if (r) {
                window.activeRegion = r;
                window.ws.setTime(r.start);
                if (window.updatePreviewMonitor) window.updatePreviewMonitor();
            }
        };

        window.onPreviewWordDblClick = function(regionId) {
            if (!window.regionsPlugin) return;
            const regions = window.regionsPlugin.getRegions();
            const r = regions.find(x => x.id === regionId);
            if (r) {
                let currentText = typeof r.content === 'string' ? r.content : (r.element ? r.element.innerText || r.element.textContent : "");
                const newText = prompt("Wort korrigieren:", currentText);
                if (newText !== null && newText.trim() !== "") {
                    r.setOptions({ content: newText.trim() });
                    window.saveState();
                    if (window.updatePreviewMonitor) window.updatePreviewMonitor();
                }
            }
        };

        window.updatePreviewMonitor = function() {
            if (!window.ws || !window.regionsPlugin) return;
            const time = window.ws.getCurrentTime();
            const monitor = document.getElementById('preview-text-container');
            if (!monitor) return;

            const regions = window.regionsPlugin.getRegions().sort((a, b) => parseFloat(a.start) - parseFloat(b.start));
            
            let lines = [];
            let currentLine = [];
            
            // 1. BULLETPROOF CHUNKING (Farberkennung)
            regions.forEach(r => {
                const colorStr = String(r.color || "").replace(/\s/g, '').toLowerCase();
                const isBlue = colorStr.includes('59,130,246') || colorStr.includes('#3b82f6');
                const isBlock = r.data?.isBlockBreak || isBlue;
                
                if (isBlock || currentLine.length === 0) {
                    if (currentLine.length > 0) lines.push(currentLine);
                    currentLine = [r];
                } else {
                    currentLine.push(r);
                }
            });
            if (currentLine.length > 0) lines.push(currentLine);

            // 2. EXAKTE ZEITFENSTER BERECHNEN (Keine Überlappungen!)
            let activeLine = null;
            for (let i = 0; i < lines.length; i++) {
                let line = lines[i];
                if (line.length === 0) continue;
                let lineStart = parseFloat(line[0].start);
                
                // Die Anzeigedauer einer Zeile endet EXAKT, wenn die nächste beginnt.
                let lineEnd = (i < lines.length - 1) ? parseFloat(lines[i+1][0].start) : parseFloat(line[line.length - 1].end) + 0.5;
                
                if (time >= lineStart && time < lineEnd) {
                    activeLine = line;
                    break;
                }
            }

            // 3. RENDER HTML
            if (activeLine) {
                let html = "";
                activeLine.forEach((r, idx) => {
                    let text = typeof r.content === 'string' ? r.content : (r.element ? r.element.innerText || r.element.textContent : "");
                    let start = parseFloat(r.start);
                    let end = parseFloat(r.end);
                    
                    let isLineBreak = r.data?.isLineBreak || (String(r.color || "").replace(/\s/g, '').toLowerCase().includes('245,158,11'));
                    if (isLineBreak) html += `<br>`;
                    
                    let cssClass = "preview-word";
                    
                    if (time >= start && time <= end) {
                        if (time <= start + 0.15) {
                            cssClass += " word-active-popup";
                        } else {
                            cssClass += " word-active-karaoke";
                        }
                    } else if (time > end) {
                        cssClass += " word-active-karaoke";
                    }
                    
                    let isSelected = (window.activeRegion && window.activeRegion.id === r.id);
                    if (isSelected) cssClass += " word-selected";
                    
                    html += `<span class="${cssClass}" 
                                style="cursor:pointer;" 
                                onclick="window.onPreviewWordClick('${r.id}')" 
                                ondblclick="window.onPreviewWordDblClick('${r.id}')">
                                ${text}
                             </span>`;
                });
                
                if (monitor.innerHTML !== html) monitor.innerHTML = html;
            } else {
                if (monitor.innerHTML !== "") monitor.innerHTML = "";
            }
        };

        // 60 FPS requestAnimationFrame Loop für absolut flüssige Sync während der Wiedergabe
        if (window.previewRafId_import) cancelAnimationFrame(window.previewRafId_import);
        const loopPreview = () => {
            if (window.ws && window.ws.isPlaying()) {
                window.updatePreviewMonitor();
            }
            window.previewRafId_import = requestAnimationFrame(loopPreview);
        };
        loopPreview();

        // Binde alle erdenklichen Time-Events für maximale Kompatibilität und Responsiveness
        ['audioprocess', 'timeupdate', 'seek', 'seeking'].forEach(evt => {
            window.ws.on(evt, window.updatePreviewMonitor);
        });
        window.regionsPlugin.on('region-update-end', window.updatePreviewMonitor);
        
        // Initiales Update beim Laden
        setTimeout(window.updatePreviewMonitor, 100);

        const dragMonitor = document.getElementById('preview-monitor');
        const dragContainer = document.getElementById('preview-text-container');
        dragContainer.style.position = 'absolute';
        if (!dragContainer.style.left) dragContainer.style.left = '50%';
        if (!dragContainer.style.top) dragContainer.style.top = '80%';
        dragContainer.style.transform = 'translate(-50%, -100%)';
        dragContainer.style.width = 'max-content';
        dragContainer.style.cursor = 'move';
        
        if (!window.dragControllerInit2) {
            window.dragControllerInit2 = true;
            window.dragController2 = {
                isDragging: false,
                down: function(e) {
                    if (e.target.tagName !== 'SPAN') window.dragController2.isDragging = true;
                },
                move: function(e) {
                    if (!window.dragController2.isDragging) return;
                    const rect = dragMonitor.getBoundingClientRect();
                    let x = e.clientX - rect.left;
                    let y = e.clientY - rect.top;
                    let px = (x / rect.width) * 100;
                    let py = (y / rect.height) * 100;
                    px = Math.max(0, Math.min(100, px));
                    py = Math.max(0, Math.min(100, py));
                    dragContainer.style.left = px + '%';
                    dragContainer.style.top = py + '%';
                },
                up: function(e) { window.dragController2.isDragging = false; }
            };
            dragMonitor.addEventListener('mousedown', window.dragController2.down);
            document.addEventListener('mousemove', window.dragController2.move);
            document.addEventListener('mouseup', window.dragController2.up);
        }
        return [];
    }
    """

    extract_btn.click(
        fn=lambda: (gr.update(selected="tab_editor"), gr.update(visible=True)),
        inputs=None,
        outputs=[tabs, loading_modal]
    ).then(
        fn=start_extraction,
        inputs=[audio_in, bg_in, keep_vocals_cb, use_original_video_cb, is_duet_cb, hf_token_input, use_syllables_cb],
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
    
    update_preview_css_js = """
    (fs, px, py) => {
        const c = document.getElementById('preview-text-container');
        if (c) {
            c.style.fontSize = fs + 'px';
            c.style.left = px + '%';
            c.style.top = py + '%';
        }
    }
    """
    font_size.change(fn=None, inputs=[font_size, pos_x, pos_y], js=update_preview_css_js)
    pos_x.change(fn=None, inputs=[font_size, pos_x, pos_y], js=update_preview_css_js)
    pos_y.change(fn=None, inputs=[font_size, pos_x, pos_y], js=update_preview_css_js)
    
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
                    return {start: r.start, end: r.end, text: textContent, color: r.color, data: r.data};
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
                            data: r.data,
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
            dummy_render_input, state_instrumental, state_bg_visual, state_audio_in, state_keep_vocals, state_use_original_video,
            color_ungesungen, color_gesungen, font_size, lead_time, pos_x, pos_y, use_entry_cues_cb, downscale_1080p_cb, input_project_name, dropdown_anim_style
        ],
        outputs=[video_out, files_out],
        js="""
        (dummy, inst, bg, aud, keep, orig, sec, prim, fsize, lead, marg, cues, down, proj, anim) => {
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
                    const isBlock = r.data?.isBlockBreak || (r.color === 'rgba(59, 130, 246, 0.5)' || r.color === 'rgb(59, 130, 246, 0.5)');
                    const isLine = r.data?.isLineBreak || (r.color === 'rgba(245, 158, 11, 0.5)' || r.color === 'rgb(245, 158, 11, 0.5)');
                    return {word: textContent, start: r.start, end: r.end, block_break: isBlock, line_break: isLine};
                });
            }
            const container = document.getElementById('preview-text-container');
            if (container) {
                if (container.style.left) px = parseFloat(container.style.left);
                if (container.style.top) py = parseFloat(container.style.top);
            }
            return [JSON.stringify(data), inst, bg, aud, keep, orig, sec, prim, fsize, lead, px, py, cues, down, proj, anim];
        }
        """
    )
    
    btn_translate.click(
        fn=translate_regions,
        inputs=[dummy_render_input, dropdown_target_lang],
        outputs=[dummy_render_input],
        js="""
        (dummy, lang) => {
            let data = [];
            if (window.regionsPlugin) {
                data = window.regionsPlugin.getRegions().map(r => {
                    let textContent = "";
                    if (typeof r.content === 'string') textContent = r.content;
                    else if (r.element) textContent = r.element.innerText || r.element.textContent;
                    return {word: textContent, start: r.start, end: r.end};
                });
            }
            return [JSON.stringify(data), lang];
        }
        """
    ).then(
        fn=None,
        inputs=[dummy_render_input],
        js="""
        (new_regions_json) => {
            if (window.ws && window.regionsPlugin) {
                let new_regions = JSON.parse(new_regions_json);
                window.regionsPlugin.clearRegions();
                new_regions.forEach(w => {
                    window.regionsPlugin.addRegion({
                        start: w.start,
                        end: w.end,
                        content: w.word,
                        color: 'rgba(16, 185, 129, 0.3)',
                        drag: true,
                        resize: true
                    });
                });
                window.saveState();
            }
        }
        """
    )
    
    btn_save_project.click(
        fn=export_wrapper,
        inputs=[dummy_render_input, media_paths_state, color_ungesungen, color_gesungen, font_size, lead_time, pos_x, pos_y, use_entry_cues_cb, downscale_1080p_cb, input_project_name, current_project_path, dropdown_anim_style],
        outputs=[current_project_path, table_projects],
        js="""
        (dummy, media_paths, cu, cg, fsize, lead, px, py, cues, down, proj, old_path, anim) => {
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
                    const isBlock = r.data?.isBlockBreak || (r.color === 'rgba(59, 130, 246, 0.5)' || r.color === 'rgb(59, 130, 246, 0.5)');
                    const isLine = r.data?.isLineBreak || (r.color === 'rgba(245, 158, 11, 0.5)' || r.color === 'rgb(245, 158, 11, 0.5)');
                    return {word: textContent, start: r.start, end: r.end, block_break: isBlock, line_break: isLine};
                });
            }
            const container = document.getElementById('preview-text-container');
            if (container) {
                if (container.style.left) px = parseFloat(container.style.left);
                if (container.style.top) py = parseFloat(container.style.top);
            }
            return [JSON.stringify(data), media_paths, cu, cg, fsize, lead, px, py, cues, down, proj, old_path, anim];
        }
        """
    )
    
    btn_save_as_project.click(
        fn=lambda *args: export_wrapper(*args[:-2], None, args[-1]),
        inputs=[dummy_render_input, media_paths_state, color_ungesungen, color_gesungen, font_size, lead_time, pos_x, pos_y, use_entry_cues_cb, downscale_1080p_cb, input_project_name, current_project_path, dropdown_anim_style],
        outputs=[current_project_path, table_projects],
        js="""
        (dummy, media_paths, cu, cg, fsize, lead, px, py, cues, down, proj, old_path, anim) => {
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
                    const isBlock = r.data?.isBlockBreak || (r.color === 'rgba(59, 130, 246, 0.5)' || r.color === 'rgb(59, 130, 246, 0.5)');
                    const isLine = r.data?.isLineBreak || (r.color === 'rgba(245, 158, 11, 0.5)' || r.color === 'rgb(245, 158, 11, 0.5)');
                    return {word: textContent, start: r.start, end: r.end, block_break: isBlock, line_break: isLine};
                });
            }
            const container = document.getElementById('preview-text-container');
            if (container) {
                if (container.style.left) px = parseFloat(container.style.left);
                if (container.style.top) py = parseFloat(container.style.top);
            }
            return [JSON.stringify(data), media_paths, cu, cg, fsize, lead, px, py, cues, down, proj, old_path, anim];
        }
        """
    )

    btn_refresh_hub.click(fn=list_projects, inputs=None, outputs=[table_projects])

    upload_import_hub.upload(
        fn=lambda: (gr.update(selected="tab_editor"), gr.update(visible=True)),
        inputs=None,
        outputs=[tabs, loading_modal]
    ).then(
        fn=import_wrapper,
        inputs=[upload_import_hub],
        outputs=[media_paths_state, words_state, color_ungesungen, color_gesungen, font_size, lead_time, pos_x, pos_y, use_entry_cues_cb, downscale_1080p_cb, track_selector, input_project_name, state_instrumental, state_bg_visual, state_audio_in, state_keep_vocals, state_use_original_video, current_project_path]
    ).then(
        fn=lambda: (gr.update(visible=False), gr.update(value=list_projects())),
        inputs=None,
        outputs=[loading_modal, table_projects]
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

    btn_auto_chunking.click(
        fn=None,
        inputs=None,
        js="(x) => { if (window.applyAutoChunking) window.applyAutoChunking(); return x; }"
    )

    btn_new_project.click(
        fn=lambda: (gr.update(selected="tab_analyse"), None),
        inputs=None,
        outputs=[tabs, current_project_path]
    )

    def delete_project(path):
        if path:
            p = Path(path)
            if p.exists():
                p.unlink()
        return gr.update(value=list_projects())

    btn_delete_project.click(
        fn=delete_project,
        inputs=[selected_project_path],
        outputs=[table_projects]
    )

    def on_project_select(evt: gr.SelectData, df):
        path = df[evt.index[0]][2]
        return gr.update(selected="tab_editor"), gr.update(visible=True), path, path

    table_projects.select(
        fn=on_project_select,
        inputs=[table_projects],
        outputs=[tabs, loading_modal, dummy_render_input, selected_project_path]
    ).then(
        fn=import_wrapper,
        inputs=[dummy_render_input],
        outputs=[media_paths_state, words_state, color_ungesungen, color_gesungen, font_size, lead_time, pos_x, pos_y, use_entry_cues_cb, downscale_1080p_cb, track_selector, input_project_name, state_instrumental, state_bg_visual, state_audio_in, state_keep_vocals, state_use_original_video, current_project_path]
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=None,
        outputs=[loading_modal]
    ).then(
        fn=None,
        inputs=[media_paths_state, words_state, track_selector],
        js=IMPORT_JS
    )

    demo.load(fn=list_projects, inputs=None, outputs=[table_projects])


if __name__ == "__main__":
    import os
    allowed = str(Path("ergebnis_ui").absolute())
    demo.launch(server_name="0.0.0.0", share=False, allowed_paths=[allowed])
