import json
from deep_translator import GoogleTranslator

def translate_regions(regions_json: str, target_lang: str = "en") -> str:
    """
    Parst die Wavesurfer Regions, fasst zusammenhängende Wörter zu Phrasen zusammen,
    übersetzt sie und gibt ein neues JSON-Array mit den übersetzten Regionen zurück.
    """
    try:
        regions = json.loads(regions_json)
    except Exception:
        return regions_json

    if not regions:
        return regions_json

    # Sortiere Regionen chronologisch
    regions.sort(key=lambda x: x.get('start', 0.0))

    phrases = []
    current_phrase = []

    for r in regions:
        if not current_phrase:
            current_phrase.append(r)
            continue
            
        last_r = current_phrase[-1]
        
        # Lücke zwischen letztem Wort und aktuellem Wort
        gap = r.get('start', 0.0) - last_r.get('end', 0.0)
        
        if gap < 1.0:
            current_phrase.append(r)
        else:
            phrases.append(current_phrase)
            current_phrase = [r]
            
    if current_phrase:
        phrases.append(current_phrase)

    translator = GoogleTranslator(source='auto', target=target_lang)
    new_regions = []

    for phrase in phrases:
        if not phrase:
            continue
            
        start_time = phrase[0].get('start', 0.0)
        end_time = phrase[-1].get('end', 0.0)
        
        # Text zusammensetzen
        phrase_text = " ".join([w.get('word', '').strip() for w in phrase if w.get('word', '').strip()])
        
        if phrase_text:
            try:
                translated_text = translator.translate(phrase_text)
            except Exception as e:
                print(f"Translation error: {e}")
                translated_text = phrase_text
                
            new_regions.append({
                "word": translated_text,
                "start": start_time,
                "end": end_time
            })

    return json.dumps(new_regions)
