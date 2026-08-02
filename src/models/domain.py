from pydantic import BaseModel

class WordTimestamp(BaseModel):
    """
    Repräsentiert ein einzelnes Wort mit seinem Start- und Endzeitpunkt im Audio.
    """
    word: str
    start: float
    end: float
