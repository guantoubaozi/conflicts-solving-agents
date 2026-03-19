from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class DebateStatus(str, Enum):
    INIT = "INIT"
    STANCE = "STANCE"
    ROUND = "ROUND"
    FINAL = "FINAL"


class Debate(BaseModel):
    debate_id: str
    proposition_id: str
    status: DebateStatus = DebateStatus.INIT
    current_round: int = 1
    created_at: datetime
    updated_at: datetime
