"""
routers/parties.py — 辩论方管理接口
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import debate_store
from models.debate import DebateStatus

router = APIRouter(prefix="/api/debates", tags=["parties"])


class AddPartyIn(BaseModel):
    name: str
    soul: str = ""


class UpdateSoulIn(BaseModel):
    soul: str = ""


@router.post("/{debate_id}/parties")
def add_party(debate_id: str, body: AddPartyIn):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")

    # 中途加入：只允许在 INIT/STANCE 阶段或一轮结束后（ROUND 阶段轮次切换时）加入
    # 具体：INIT 或 STANCE 阶段可直接加入；ROUND 阶段也允许（中途加入）
    if debate.status == DebateStatus.FINAL:
        raise HTTPException(status_code=400, detail="debate is already in FINAL stage")

    soul = body.soul[:200] if body.soul else ""
    joined_round = debate.current_round if debate.status == DebateStatus.ROUND else 0
    party = debate_store.add_party(debate_id, body.name, joined_round, soul)

    # 首个辩论方加入时，将辩论状态推进到 STANCE
    if debate.status == DebateStatus.INIT:
        from datetime import datetime, timezone
        debate.status = DebateStatus.STANCE
        debate.updated_at = datetime.now(timezone.utc)
        debate_store.save_debate(debate)

    return party.model_dump(mode="json")


@router.get("/{debate_id}/parties")
def list_parties(debate_id: str):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    parties = debate_store.get_parties(debate_id)
    return [p.model_dump(mode="json") for p in parties]


@router.put("/{debate_id}/parties/{party_id}/soul")
def update_soul(debate_id: str, party_id: str, body: UpdateSoulIn):
    party = debate_store.get_party(debate_id, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")
    party.soul = body.soul[:200] if body.soul else ""
    debate_store.save_party(party)
    return party.model_dump(mode="json")
