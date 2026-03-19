"""
services/debate_store.py — 辩论场次的持久化 CRUD（不含 Agent 逻辑）
"""

import uuid
from datetime import datetime, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import storage
from models.debate import Debate, DebateStatus
from models.proposition import Proposition
from models.party import Party, PartyStatus
from models.stance import Stance, EvidenceItem, CompressStatus
from models.solution import Solution
from models.judge_summary import JudgeSummary
from models.debate_round import DebateRound, RoundPhase
from models.changelog import ChangeLog


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 辩论场次 ───────────────────────────────────────────────

def create_debate(proposition_content: str, created_by: str, background: str = "") -> tuple[Debate, Proposition]:
    debate_id = str(uuid.uuid4())
    proposition_id = str(uuid.uuid4())
    now = _now()

    debate = Debate(
        debate_id=debate_id,
        proposition_id=proposition_id,
        status=DebateStatus.INIT,
        current_round=1,
        created_at=now,
        updated_at=now,
    )
    proposition = Proposition(
        proposition_id=proposition_id,
        debate_id=debate_id,
        content=proposition_content,
        background=background,
        created_by=created_by,
        created_at=now,
    )

    storage.write_debate_state(debate_id, debate.model_dump(mode="json"))
    storage.write_proposition(debate_id, proposition.model_dump(mode="json"))
    return debate, proposition


def get_debate(debate_id: str) -> Debate | None:
    data = storage.read_debate_state(debate_id)
    if data is None:
        return None
    return Debate.model_validate(data)


def save_debate(debate: Debate) -> None:
    # 保留 debate_state.json 中的额外字段（party_details 等），只更新 Debate 模型字段
    existing = storage.read_debate_state(debate.debate_id) or {}
    existing.update(debate.model_dump(mode="json"))
    storage.write_debate_state(debate.debate_id, existing)


def list_debates() -> list[Debate]:
    result = []
    for did in storage.list_debate_ids():
        d = get_debate(did)
        if d:
            result.append(d)
    return result


def delete_debate(debate_id: str) -> bool:
    """删除辩论及其所有关联文件。"""
    return storage.delete_debate_dir(debate_id)


def get_proposition(debate_id: str) -> Proposition | None:
    data = storage.read_proposition(debate_id)
    if data is None:
        return None
    return Proposition.model_validate(data)


# ── 辩论方 ─────────────────────────────────────────────────

def _parties_key(debate_id: str) -> dict:
    """从 debate_state 中读取 parties 列表（存储为 party_id 列表）。"""
    data = storage.read_debate_state(debate_id)
    return data.get("parties", []) if data else []


def add_party(debate_id: str, name: str, joined_round: int = 0, soul: str = "") -> Party:
    party_id = str(uuid.uuid4())
    party = Party(
        party_id=party_id,
        debate_id=debate_id,
        name=name,
        soul=soul,
        joined_round=joined_round,
        status=PartyStatus.ACTIVE,
    )
    # 持久化 party 信息到 debate_state 的 party_details
    state = storage.read_debate_state(debate_id) or {}
    party_details = state.get("party_details", {})
    party_details[party_id] = party.model_dump(mode="json")
    parties_list = state.get("parties", [])
    if party_id not in parties_list:
        parties_list.append(party_id)
    state["parties"] = parties_list
    state["party_details"] = party_details
    storage.write_debate_state(debate_id, state)
    return party


def get_parties(debate_id: str) -> list[Party]:
    state = storage.read_debate_state(debate_id) or {}
    party_details = state.get("party_details", {})
    return [Party.model_validate(v) for v in party_details.values()]


def get_party(debate_id: str, party_id: str) -> Party | None:
    state = storage.read_debate_state(debate_id) or {}
    party_details = state.get("party_details", {})
    data = party_details.get(party_id)
    if data is None:
        return None
    return Party.model_validate(data)


def save_party(party: Party) -> None:
    state = storage.read_debate_state(party.debate_id) or {}
    party_details = state.get("party_details", {})
    party_details[party.party_id] = party.model_dump(mode="json")
    state["party_details"] = party_details
    storage.write_debate_state(party.debate_id, state)


# ── 立论 ───────────────────────────────────────────────────

def save_stance(stance: Stance) -> None:
    storage.write_stance(stance.debate_id, stance.party_id, stance.model_dump(mode="json"))


def get_stance(debate_id: str, party_id: str) -> Stance | None:
    data = storage.read_stance(debate_id, party_id)
    if data is None:
        return None
    return Stance.model_validate(data)


# ── 解决方案 ───────────────────────────────────────────────

def save_solution(solution: Solution) -> None:
    storage.write_solution(solution.debate_id, solution.round, solution.party_id, solution.model_dump(mode="json"))


def get_solution(debate_id: str, round_num: int, party_id: str) -> Solution | None:
    data = storage.read_solution(debate_id, round_num, party_id)
    if data is None:
        return None
    return Solution.model_validate(data)


def get_round_solutions(debate_id: str, round_num: int) -> list[Solution]:
    state = storage.read_debate_state(debate_id) or {}
    party_ids = state.get("parties", [])
    result = []
    for pid in party_ids:
        sol = get_solution(debate_id, round_num, pid)
        if sol:
            result.append(sol)
    return result


# ── 裁判梳理 ───────────────────────────────────────────────

def save_judge_summary(summary: JudgeSummary) -> None:
    storage.write_judge_summary(summary.debate_id, summary.round, summary.model_dump(mode="json"))


def get_judge_summary(debate_id: str, round_num: int) -> JudgeSummary | None:
    data = storage.read_judge_summary(debate_id, round_num)
    if data is None:
        return None
    return JudgeSummary.model_validate(data)


# ── 轮次状态 ───────────────────────────────────────────────

def save_round_state(round_obj: DebateRound) -> None:
    storage.write_round_state(round_obj.debate_id, round_obj.round, round_obj.model_dump(mode="json"))


def get_round_state(debate_id: str, round_num: int) -> DebateRound | None:
    data = storage.read_round_state(debate_id, round_num)
    if data is None:
        return None
    return DebateRound.model_validate(data)


def init_round(debate_id: str, round_num: int) -> DebateRound:
    round_id = str(uuid.uuid4())
    now = _now()
    r = DebateRound(
        round_id=round_id,
        debate_id=debate_id,
        round=round_num,
        status=RoundPhase.SOLUTION,
        human_confirmed=[],
        created_at=now,
    )
    save_round_state(r)
    return r


# ── 变更记录 ───────────────────────────────────────────────

def append_changelog(log: ChangeLog) -> None:
    logs = storage.read_changelogs(log.debate_id, log.party_id)
    logs.append(log.model_dump(mode="json"))
    storage.write_changelogs(log.debate_id, log.party_id, logs)


def get_changelogs(debate_id: str, party_id: str) -> list[ChangeLog]:
    raw = storage.read_changelogs(debate_id, party_id)
    return [ChangeLog.model_validate(r) for r in raw]
