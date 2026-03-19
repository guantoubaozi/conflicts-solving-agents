from datetime import datetime
from pydantic import BaseModel


class Proposition(BaseModel):
    proposition_id: str
    debate_id: str
    content: str
    background: str = ""   # 题目背景，≤200字，选填
    created_by: str
    created_at: datetime
