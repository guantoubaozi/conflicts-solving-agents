from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class ChangeType(str, Enum):
    MODIFY_FACT = "MODIFY_FACT"
    MODIFY_EVIDENCE = "MODIFY_EVIDENCE"
    ABANDON_EVIDENCE = "ABANDON_EVIDENCE"


class ChangeLog(BaseModel):
    log_id: str
    debate_id: str
    party_id: str
    round: int
    change_type: ChangeType
    target_id: str
    reason: str
    before_content: str
    after_content: str = ""
    created_at: datetime
