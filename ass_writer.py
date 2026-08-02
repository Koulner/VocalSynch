from pathlib import Path
from models import WordTimestamp

# ASS Styling Header
# Erzeugt ein modernes, zentriertes Styling im unteren Drittel
# PrimaryColour (ausgefüllt/gesungen): &H0000FFFF (Neon-Gelb in AABBGGRR)
# SecondaryColour (vor dem Singen): &H00FFFFFF (Weiß)
# Outline=3, Shadow=2 für maximalen Kontrast, Size=36 für Textdichte
ASS_HEADER = """[Script Info]
Title: Videoke Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,36,&H0000FFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def format_ass_time(seconds: float) -> str:
    """
    Konvertiert Sekunden in das H:MM:SS.cs Format (Stunden:Minuten:Sekunden.Hundertstelsekunden).
    Beispiel: 65.525 -> 0:01:05.53
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    # Runden auf Hundertstel
    cs = int(round((seconds % 1) * 100))
    
    # Überlauf von cs abfangen
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

def generate_karaoke_ass(timestamps: list[WordTimestamp], output_path: Path):
    """
    Gruppiert WordTimestamps in sinnvolle Zeilen und generiert die .ass Datei 
    mit Karaoke-Tags ({\kXX}).
    """
    lines = []
    current_line_words = []
    
    # Wort-Gruppierung (Umbruch wenn Pause > 1.2s oder max 14 Wörter pro Zeile)
    for wt in timestamps:
        if not current_line_words:
            current_line_words.append(wt)
            continue
            
        prev_wt = current_line_words[-1]
        pause = wt.start - prev_wt.end
        
        if pause > 1.2 or len(current_line_words) >= 14:
            lines.append(current_line_words)
            current_line_words = [wt]
        else:
            current_line_words.append(wt)
            
    if current_line_words:
        lines.append(current_line_words)
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ASS_HEADER)
        
        for line_words in lines:
            first_word_start = line_words[0].start
            
            # Setze die Start-Zeit des Zeilen-Events exakt 1.5s vor das erste Wort (mindestens 0.0)
            line_start_time = max(0.0, first_word_start - 1.5)
            
            line_start = format_ass_time(line_start_time)
            line_end = format_ass_time(line_words[-1].end)
            
            # Berechne den Delay zwischen dem Einblenden der Zeile und dem Beginn des Gesangs
            delay_cs = int(round((first_word_start - line_start_time) * 100))
            
            # Füge das Leerzeichen-Delay am Anfang ein
            ass_text = f"{{\\k{delay_cs}}} "
            
            for wt in line_words:
                # Dauer in Hundertstelsekunden für den \k Tag berechnen
                duration_cs = int(round((wt.end - wt.start) * 100))
                ass_text += f"{{\\k{duration_cs}}}{wt.word} "
                
            # Wir nutzen rstrip() (rechts strippen), damit das anfängliche Leerzeichen-Delay erhalten bleibt!
            ass_text = ass_text.rstrip()
            
            # Dialogue Zeile in die Datei schreiben
            f.write(f"Dialogue: 0,{line_start},{line_end},Karaoke,,0,0,0,,{ass_text}\n")
