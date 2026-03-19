"""
models/__init__.py — 数据模型包
"""

from .debate import Debate, DebateStatus
from .proposition import Proposition
from .party import Party, PartyStatus
from .stance import Stance, EvidenceItem, CompressStatus
from .solution import Solution
from .judge_summary import JudgeSummary
from .debate_round import DebateRound, RoundPhase
from .changelog import ChangeLog, ChangeType

__all__ = [
    "Debate", "DebateStatus",
    "Proposition",
    "Party", "PartyStatus",
    "Stance", "EvidenceItem", "CompressStatus",
    "Solution",
    "JudgeSummary",
    "DebateRound", "RoundPhase",
    "ChangeLog", "ChangeType",
]
