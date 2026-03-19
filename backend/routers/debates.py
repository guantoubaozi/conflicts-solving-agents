"""
routers/debates.py — 辩论场次相关接口
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import debate_store
from models.debate import DebateStatus

router = APIRouter(prefix="/api/debates", tags=["debates"])


class CreateDebateIn(BaseModel):
    proposition: str
    created_by: str = "anonymous"
    background: str = ""


@router.post("")
def create_debate(body: CreateDebateIn):
    debate, proposition = debate_store.create_debate(body.proposition, body.created_by, body.background)
    return {"debate_id": debate.debate_id, "proposition_id": debate.proposition_id}


@router.get("")
def list_debates():
    debates = debate_store.list_debates()
    result = []
    for d in debates:
        prop = debate_store.get_proposition(d.debate_id)
        result.append({
            "debate_id": d.debate_id,
            "proposition": prop.content if prop else "",
            "status": d.status,
            "current_round": d.current_round,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        })
    return result


@router.get("/{debate_id}")
def get_debate(debate_id: str):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    prop = debate_store.get_proposition(debate_id)
    parties = debate_store.get_parties(debate_id)
    round_state = debate_store.get_round_state(debate_id, debate.current_round)
    return {
        "debate_id": debate.debate_id,
        "proposition": prop.model_dump(mode="json") if prop else None,
        "status": debate.status,
        "current_round": debate.current_round,
        "current_round_phase": round_state.status if round_state else None,
        "ai_running": round_state.ai_running if round_state else False,
        "final_request_by": round_state.final_request_by if round_state else None,
        "final_request_votes": round_state.final_request_votes if round_state else {},
        "parties": [p.model_dump(mode="json") for p in parties],
        "created_at": debate.created_at,
        "updated_at": debate.updated_at,
    }


@router.delete("/{debate_id}")
def delete_debate(debate_id: str):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    debate_store.delete_debate(debate_id)
    return {"ok": True}


@router.post("/{debate_id}/start")
def start_debate(debate_id: str):
    """立论完成后触发，将辩论状态从 STANCE 推进到 ROUND。"""
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.status != DebateStatus.STANCE:
        raise HTTPException(status_code=400, detail=f"debate is in {debate.status}, expected STANCE")

    parties = debate_store.get_parties(debate_id)
    for p in parties:
        stance = debate_store.get_stance(debate_id, p.party_id)
        if not stance:
            raise HTTPException(status_code=400, detail=f"party {p.party_id} has not submitted stance")

    from datetime import timezone
    from datetime import datetime
    debate.status = DebateStatus.ROUND
    debate.updated_at = datetime.now(timezone.utc)
    debate_store.save_debate(debate)
    debate_store.init_round(debate_id, 1)
    return {"ok": True, "status": debate.status}


class UpdateBackgroundIn(BaseModel):
    background: str


@router.put("/{debate_id}/background")
def update_background(debate_id: str, body: UpdateBackgroundIn):
    """修改题目背景（仅 INIT/STANCE 状态允许）。"""
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.status not in (DebateStatus.INIT, DebateStatus.STANCE):
        raise HTTPException(status_code=400, detail="background can only be edited in INIT or STANCE status")
    if len(body.background) > 200:
        raise HTTPException(status_code=400, detail="background must be ≤200 characters")

    prop = debate_store.get_proposition(debate_id)
    if not prop:
        raise HTTPException(status_code=404, detail="proposition not found")
    prop.background = body.background
    from services import storage
    storage.write_proposition(debate_id, prop.model_dump(mode="json"))
    return {"ok": True}
