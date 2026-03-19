from enum import Enum
from pydantic import BaseModel


class PartyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CONFIRMED = "CONFIRMED"


class Party(BaseModel):
    party_id: str
    debate_id: str
    name: str
    soul: str = ""  # 辩论方性格，≤200字，影响 Agent 思考方式
    joined_round: int = 0
    status: PartyStatus = PartyStatus.ACTIVE
