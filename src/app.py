import gradio as gr
from pathlib import Path
from src.main import prepare_input, VideokePipeline
from src.core.config import VideokeConfig

def process_ui(audio_input, bg_input, progress=gr.Progress()):
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
        
    pipeline = VideokePipeline(config=config, input_path=actual_audio, output_dir=output_dir, bg_visual=actual_bg_visual)
    
    final_results = None
    for status in pipeline.run():
        if isinstance(status, str):
            progress(0.5, desc=status)
        elif isinstance(status, dict):
            final_results = status
            
    if not final_results:
        raise gr.Error("Ein Fehler ist aufgetreten.")
        
    return (
        str(final_results["video"]),
        gr.update(value=[str(final_results["video"]), str(final_results["instrumental"]), str(final_results["ass"])], visible=True)
    )

with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🎤 Auto-Videoke Creator")
    
    with gr.Row():
        with gr.Column(scale=1):
            audio_in = gr.Audio(type="filepath", label="Song (MP3/WAV/MP4)")
            bg_in = gr.Image(type="filepath", label="Hintergrundbild (Optional)")
            
            with gr.Accordion("Erweiterte Einstellungen", open=False):
                gr.Markdown("*(Einstellungen werden aus configs/default.yaml geladen)*")
                
            submit_btn = gr.Button("Videoke generieren", variant="primary")
            
        with gr.Column(scale=1):
            video_out = gr.Video(label="Dein Karaoke-Video")
            files_out = gr.File(label="Generierte Assets", visible=False, file_count="multiple")
            
    submit_btn.click(
        fn=process_ui,
        inputs=[audio_in, bg_in],
        outputs=[video_out, files_out]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", share=False)
