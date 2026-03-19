from datetime import datetime
from pydantic import BaseModel


class Solution(BaseModel):
    solution_id: str
    debate_id: str
    party_id: str
    round: int
    content: str
    is_valid: bool = True
    invalid_reason: str = ""
    created_at: datetime
