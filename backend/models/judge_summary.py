from datetime import datetime
from pydantic import BaseModel


class JudgeSummary(BaseModel):
    summary_id: str
    debate_id: str
    round: int
    consensus: str
    contradictions: str
    combined_solution: str
    has_contradiction: bool
    focus_next: str = ""          # 下一轮应聚焦解决的核心矛盾（裁判指定）
    locked_consensus: str = ""    # 累积锁定的共识（各方不得再挑战）
    created_at: datetime
