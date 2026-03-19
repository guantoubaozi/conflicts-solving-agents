from datetime import datetime
from enum import Enum
from typing import List
from pydantic import BaseModel


class CompressStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    COMPRESSING = "COMPRESSING"
    DONE = "DONE"


class EvidenceItem(BaseModel):
    evidence_id: str
    content: str
    is_valid: bool = True
    created_round: int
    compress_status: CompressStatus = CompressStatus.NONE


class Stance(BaseModel):
    stance_id: str
    party_id: str
    debate_id: str
    viewpoint: str
    facts: str = ""
    facts_organizing: bool = False  # T4: 事实整理进行中标志
    evidence_pool: List[EvidenceItem] = []
    created_at: datetime
    updated_at: datetime
