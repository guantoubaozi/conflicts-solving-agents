"""
routers/changelogs.py — 变更记录接口
"""

from fastapi import APIRouter, HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import debate_store

router = APIRouter(prefix="/api/debates", tags=["changelogs"])


@router.get("/{debate_id}/parties/{party_id}/changelogs")
def get_changelogs(debate_id: str, party_id: str):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    logs = debate_store.get_changelogs(debate_id, party_id)
    return [l.model_dump(mode="json") for l in logs]
