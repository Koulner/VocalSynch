import sys
from pathlib import Path

# Fix: Setze den Root-Pfad des Projekts in den sys.path, 
# damit absolute Imports via 'src.XXX' funktionieren.
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import gradio as gr
import pandas as pd
from src.main import prepare_input, VideokePipeline
from src.core.config import VideokeConfig
from src.models.domain import WordTimestamp

def hex_to_ass_color(hex_rgb: str) -> str:
    """Konvertiert Gradio RGB Hex (#RRGGBB) zu ASS BGR Hex (&H00BBGGRR)."""
    hex_rgb = hex_rgb.lstrip('#')
    if len(hex_rgb) == 6:
        r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"

def start_extraction(audio_input, bg_input, keep_vocals, use_original_video, is_duet, hf_token, progress=gr.Progress()):
    if not audio_input:
        raise gr.Error("Bitte lade eine Audio- oder Videodatei hoch.")
        
    output_dir = Path("ergebnis_ui")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    input_path = Path(audio_input)
    bg_visual = Path(bg_input) if bg_input else None
    
    progress(0.1, desc="Audio extrahieren (falls Video)...")
    actual_audio, actual_bg_visual = prepare_input(input_path, output_dir)
    
    if bg_visual and not actual_bg_visual:
        actual_bg_visual = bg_visual
        
    config = VideokeConfig.load("configs/default.yaml")
    if is_duet and hf_token:
        config.text.hf_token = hf_token
        
    pipeline = VideokePipeline(config=config, input_path=actual_audio, output_dir=output_dir, bg_visual=actual_bg_visual)
    
    instrumental_path = None
    timestamps = []
    
    for status in pipeline.run_extraction(keep_vocals=keep_vocals):
        if isinstance(status, str):
            progress(0.5, desc=status)
        elif isinstance(status, dict):
            instrumental_path = status["instrumental"]
            timestamps = status["timestamps"]
            
    if not instrumental_path or not timestamps:
        raise gr.Error("Ein Fehler ist bei der Extraktion aufgetreten.")
        
    df_data = pd.DataFrame([[wt.word, wt.start, wt.end, wt.speaker or ""] for wt in timestamps], columns=["Wort", "Start", "Ende", "Sprecher"])
    
    return (
        df_data,
        str(instrumental_path), 
        str(actual_bg_visual) if actual_bg_visual else None,
        str(actual_audio),
        keep_vocals,
        use_original_video,
        gr.Tabs(selected="tab_editor")
    )

def start_rendering(df, instrumental_path_str, bg_visual_str, audio_in_str, keep_vocals, use_original_video,
                   secondary_color, primary_color, font_size, lead_time, margin_v, progress=gr.Progress()):
    if not instrumental_path_str or df is None:
        raise gr.Error("Keine Extraktionsdaten gefunden. Bitte starte bei Schritt 1.")
        
    instrumental_path = Path(instrumental_path_str)
    bg_visual = Path(bg_visual_str) if bg_visual_str else None
    input_path = Path(audio_in_str)
    output_dir = Path("ergebnis_ui")
    
    config = VideokeConfig.load("configs/default.yaml")
    
    timestamps = []
    for _, row in df.iterrows():
        word = str(row["Wort"])
        start = float(row["Start"])
        end = float(row["Ende"])
        speaker = str(row["Sprecher"]) if "Sprecher" in row and pd.notna(row["Sprecher"]) and str(row["Sprecher"]).strip() != "" else None
        timestamps.append(WordTimestamp(word=word, start=start, end=end, speaker=speaker))
        
    config.video.style.primary_colour = hex_to_ass_color(secondary_color)
    config.video.style.secondary_colour = hex_to_ass_color(primary_color)
    config.video.style.font_size = int(font_size)
    config.video.style.margin_v = int(margin_v)
    config.video.ass.lead_time_seconds = float(lead_time)
    
    pipeline = VideokePipeline(config=config, input_path=input_path, output_dir=output_dir, bg_visual=bg_visual)
    
    final_results = None
    for status in pipeline.run_rendering(instrumental_path, timestamps, override_config=config, use_original_video=use_original_video):
        if isinstance(status, str):
            progress(0.8, desc=status)
        elif isinstance(status, dict):
            final_results = status
            
    if not final_results:
        raise gr.Error("Fehler beim Rendering.")
        
    return (
        str(final_results["video"]),
        gr.update(value=[str(final_results["video"]), str(final_results["instrumental"]), str(final_results["ass"])], visible=True)
    )

with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🎤 Auto-Videoke Creator (Human-in-the-Loop)")
    
    state_instrumental = gr.State()
    state_bg_visual = gr.State()
    state_audio_in = gr.State()
    state_keep_vocals = gr.State()
    state_use_original_video = gr.State()
    
    with gr.Tabs() as tabs:
        with gr.Tab("Schritt 1: Analyse", id="tab_analyse"):
            with gr.Row():
                with gr.Column(scale=1):
                    audio_in = gr.File(label="Song (MP3/WAV/MP4)", file_types=[".mp3", ".wav", ".flac", ".mp4", ".mov", ".mkv"])
                    bg_in = gr.Image(type="filepath", label="Hintergrundbild (Optional)")
                    
                    keep_vocals_cb = gr.Checkbox(label="Nur Untertitel generieren, Original-Audio behalten", value=False)
                    use_original_video_cb = gr.Checkbox(label="Untertitel auf Original-Video legen", value=False)
                    
                    is_duet_cb = gr.Checkbox(label="Duett-Modus / Mehrere Sprecher (WhisperX Diarization)", value=False)
                    hf_token_input = gr.Textbox(type="password", label="Hugging Face Token", visible=False)
                    
                    is_duet_cb.change(fn=lambda x: gr.update(visible=x), inputs=[is_duet_cb], outputs=[hf_token_input])
                    
                    extract_btn = gr.Button("Analyse starten", variant="primary")
                    
        with gr.Tab("Schritt 2: Editor & Render", id="tab_editor"):
            with gr.Row():
                with gr.Column(scale=2):
                    gr.Markdown("### WhisperX Timestamps Editor")
                    words_df = gr.Dataframe(
                        headers=["Wort", "Start", "Ende", "Sprecher"],
                        datatype=["str", "number", "number", "str"],
                        interactive=True,
                        wrap=True
                    )
                    
                with gr.Column(scale=1):
                    gr.Markdown("### Visuelle Settings")
                    secondary_color = gr.ColorPicker(label="Standardfarbe (Primary)", value="#00FFFF")
                    primary_color = gr.ColorPicker(label="Highlightfarbe (Secondary)", value="#FFFFFF")
                    font_size = gr.Slider(minimum=20, maximum=100, step=1, label="Schriftgröße", value=36)
                    lead_time = gr.Slider(minimum=0.0, maximum=3.0, step=0.1, label="Lead-Time (Sek.)", value=1.5)
                    margin_v = gr.Slider(minimum=0, maximum=200, step=1, label="Vertikaler Abstand (MarginV)", value=50)
                    
                    render_btn = gr.Button("Video jetzt rendern", variant="primary")
                    
            with gr.Row():
                with gr.Column():
                    video_out = gr.Video(label="Dein Karaoke-Video")
                    files_out = gr.File(label="Generierte Assets", visible=False, file_count="multiple")
            
    extract_btn.click(
        fn=start_extraction,
        inputs=[audio_in, bg_in, keep_vocals_cb, use_original_video_cb, is_duet_cb, hf_token_input],
        outputs=[words_df, state_instrumental, state_bg_visual, state_audio_in, state_keep_vocals, state_use_original_video, tabs]
    )
    
    render_btn.click(
        fn=start_rendering,
        inputs=[
            words_df, state_instrumental, state_bg_visual, state_audio_in, state_keep_vocals, state_use_original_video,
            secondary_color, primary_color, font_size, lead_time, margin_v
        ],
        outputs=[video_out, files_out]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", share=False)
