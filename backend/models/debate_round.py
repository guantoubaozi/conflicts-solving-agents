from datetime import datetime
from enum import Enum
from typing import List
from pydantic import BaseModel


class RoundPhase(str, Enum):
    SOLUTION = "SOLUTION"
    JUDGE = "JUDGE"
    DEBATE = "DEBATE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    DONE = "DONE"


class DebateRound(BaseModel):
    round_id: str
    debate_id: str
    round: int
    status: RoundPhase = RoundPhase.SOLUTION
    human_confirmed: List[str] = []
    ai_running: bool = False                      # AI 后台任务是否正在执行
    final_request_by: str | None = None          # T6: 发起终论申请的 party_id
    final_request_votes: dict[str, bool] = {}    # T6: {party_id: True/False}
    created_at: datetime
    completed_at: datetime | None = None
