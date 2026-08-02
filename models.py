from pydantic import BaseModel

class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
