from pydantic import BaseModel
from typing import Optional

class WordTimestamp(BaseModel):
    """
    Repräsentiert ein einzelnes Wort mit seinem Start- und Endzeitpunkt im Audio.
    """
    word: str
    start: float
    end: float
    speaker: Optional[str] = None
    append_space: bool = True
    line_break: bool = False
