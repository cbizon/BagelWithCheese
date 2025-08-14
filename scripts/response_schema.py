from pydantic import BaseModel
from typing import List, Literal

class CandidateResponse(BaseModel):
    candidate: str
    color_code: str
    vocabulary_class: str
    evaluation: str
    relation_type: Literal ['exact', 'superclass', 'subclass', 'related', 'none']

class Response(BaseModel):
    reasoning: str
    candidates: List[CandidateResponse]

