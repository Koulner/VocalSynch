from pathlib import Path
from src.models.domain import WordTimestamp
from src.core.config import VideokeConfig

def format_ass_time(seconds: float) -> str:
    """
    Konvertiert Sekunden in das H:MM:SS.cs Format.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    
    if cs >= 100:
        cs = 0
        secs += 1
        if secs >= 60:
            secs = 0
            minutes += 1
            if minutes >= 60:
                minutes = 0
                hours += 1
                
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"

def generate_karaoke_ass(timestamps: list[WordTimestamp], output_path: Path, config: VideokeConfig):
    """
    Gruppiert WordTimestamps in sinnvolle Zeilen und generiert die .ass Datei 
    anhand der übergebenen VideokeConfig.
    """
    lines = []
    current_line_words = []
    
    max_pause = config.video.ass.max_pause_seconds
    max_words = config.video.ass.max_words_per_line
    
    # Wort-Gruppierung
    for wt in timestamps:
        if not current_line_words:
            current_line_words.append(wt)
            continue
            
        prev_wt = current_line_words[-1]
        pause = wt.start - prev_wt.end
        
        # Zeilenumbruch wenn Pause zu lang, Limit erreicht oder Speaker wechselt
        speaker_changed = (wt.speaker != prev_wt.speaker)
        
        if pause > max_pause or len(current_line_words) >= max_words or speaker_changed:
            lines.append(current_line_words)
            current_line_words = [wt]
        else:
            current_line_words.append(wt)
            
    if current_line_words:
        lines.append(current_line_words)
        
    # Dynamisch Styles für erkannte Speaker generieren
    unique_speakers = list(set([wt.speaker for wt in timestamps if wt.speaker]))
    unique_speakers.sort()
    
    style = config.video.style
    play_res_x = config.video.ass.play_res_x
    play_res_y = config.video.ass.play_res_y
    
    # MarginV als Prozent relativ zur Videohöhe
    margin_v_abs = int(play_res_y * (style.margin_v / 100.0))
    
    # Basis-Style
    styles_str = f"Style: Karaoke,Arial,{style.font_size},{style.primary_colour},{style.secondary_colour},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},2,10,10,{margin_v_abs},1\n"
    
    # Speaker-Styles
    for i, spk in enumerate(unique_speakers):
        spk_color = style.duet_colours[i % len(style.duet_colours)]
        styles_str += f"Style: Karaoke_{spk},Arial,{style.font_size},{spk_color},{style.secondary_colour},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},2,10,10,{margin_v_abs},1\n"
        
    ass_header = f"""[Script Info]
Title: Videoke Karaoke Subtitles
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles_str.strip()}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        
        lead_time = config.video.ass.lead_time_seconds
        use_cues = config.video.ass.use_entry_cues
        
        for i, line_words in enumerate(lines):
            first_word_start = line_words[0].start
            
            # Basis Line Start Time
            line_start_time = max(0.0, first_word_start - lead_time)
            if i > 0:
                line_start_time = max(line_start_time, lines[i-1][-1].end)
                
            line_start = format_ass_time(line_start_time)
            line_end = format_ass_time(line_words[-1].end)
                
            ass_text = ""
            
            # Entry Cue Logik
            show_cue = False
            if use_cues:
                if i == 0 or (first_word_start - lines[i-1][-1].end > 4.0):
                    if first_word_start - line_start_time >= 1.5:
                        show_cue = True
            
            total_delay_cs = int(round((first_word_start - line_start_time) * 100))
            
            if show_cue:
                rest_delay = max(0, total_delay_cs - 150)
                if rest_delay > 0:
                    ass_text += f"{{\\k{rest_delay}}}"
                ass_text += "{\\kf50}• {\\kf50}• {\\kf50}• "
            else:
                ass_text += f"{{\\k{total_delay_cs}}} "
            
            prev_end = None
            for wt in line_words:
                if prev_end is not None:
                    gap = wt.start - prev_end
                    if gap > 0.1:
                        gap_cs = int(round(gap * 100))
                        ass_text += f"{{\\k{gap_cs}}} "
                        
                duration_cs = int(round((wt.end - wt.start) * 100))
                space = " " if wt.append_space else ""
                ass_text += f"{{\\kf{duration_cs}}}{wt.word}{space}"
                prev_end = wt.end
                
            ass_text = ass_text.rstrip()
            
            line_style = "Karaoke"
            if line_words[0].speaker:
                line_style = f"Karaoke_{line_words[0].speaker}"
            
            f.write(f"Dialogue: 0,{line_start},{line_end},{line_style},,0,0,0,,{ass_text}\n")
