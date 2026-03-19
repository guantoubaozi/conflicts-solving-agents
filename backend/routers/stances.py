"""
routers/stances.py — 立论接口
"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import debate_store
from models.stance import Stance, EvidenceItem, CompressStatus
from models.debate import DebateStatus

router = APIRouter(prefix="/api/debates", tags=["stances"])

MAX_VIEWPOINT = 200
MAX_FACTS = 1000


class EvidenceIn(BaseModel):
    content: str


class StanceIn(BaseModel):
    viewpoint: str
    facts: str = ""
    evidence_pool: List[EvidenceIn] = []

    @field_validator("viewpoint")
    @classmethod
    def check_viewpoint(cls, v: str) -> str:
        if len(v) > MAX_VIEWPOINT:
            raise ValueError(f"观点不得超过 {MAX_VIEWPOINT} 字，当前 {len(v)} 字")
        return v

    @field_validator("facts")
    @classmethod
    def check_facts(cls, v: str) -> str:
        if len(v) > MAX_FACTS:
            raise ValueError(f"事实不得超过 {MAX_FACTS} 字，当前 {len(v)} 字")
        return v


class AppendFactIn(BaseModel):
    content: str
    round: int


@router.post("/{debate_id}/parties/{party_id}/stance")
def submit_stance(debate_id: str, party_id: str, body: StanceIn):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.status not in (DebateStatus.STANCE, DebateStatus.ROUND):
        raise HTTPException(status_code=400, detail=f"cannot submit stance in status {debate.status}")

    party = debate_store.get_party(debate_id, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")

    now = datetime.now(timezone.utc)
    existing = debate_store.get_stance(debate_id, party_id)
    stance_id = existing.stance_id if existing else str(uuid.uuid4())
    current_round = debate.current_round

    evidence_items = []
    for e in body.evidence_pool:
        eid = str(uuid.uuid4())
        compress_status = CompressStatus.NONE
        if len(e.content) > 5000:
            compress_status = CompressStatus.PENDING
        evidence_items.append(EvidenceItem(
            evidence_id=eid,
            content=e.content,
            is_valid=True,
            created_round=current_round,
            compress_status=compress_status,
        ))

    stance = Stance(
        stance_id=stance_id,
        party_id=party_id,
        debate_id=debate_id,
        viewpoint=body.viewpoint,
        facts=body.facts,
        evidence_pool=evidence_items,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    debate_store.save_stance(stance)
    return stance.model_dump(mode="json")


@router.get("/{debate_id}/parties/{party_id}/stance")
def get_stance(debate_id: str, party_id: str):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    stance = debate_store.get_stance(debate_id, party_id)
    if not stance:
        raise HTTPException(status_code=404, detail="stance not found")
    return stance.model_dump(mode="json")


@router.post("/{debate_id}/parties/{party_id}/facts/append")
def append_fact(debate_id: str, party_id: str, body: AppendFactIn):
    """追加事实到己方事实库，触发异步 LLM 整理。"""
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.status != DebateStatus.ROUND:
        raise HTTPException(status_code=400, detail="can only append facts during ROUND status")

    stance = debate_store.get_stance(debate_id, party_id)
    if not stance:
        raise HTTPException(status_code=404, detail="stance not found")

    if stance.facts_organizing:
        raise HTTPException(status_code=409, detail="facts are being organized, please wait")

    if not body.content.strip():
        raise HTTPException(status_code=400, detail="content cannot be empty")

    # 追加事实
    now = datetime.now(timezone.utc)
    separator = "\n" if stance.facts.strip() else ""
    stance.facts = stance.facts.rstrip() + separator + body.content.strip()
    stance.facts_organizing = True
    stance.updated_at = now
    debate_store.save_stance(stance)

    # 触发异步 LLM 整理
    import threading
    import asyncio

    def _run_organize():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_organize_facts(debate_id, party_id))
        finally:
            loop.close()

    t = threading.Thread(target=_run_organize, daemon=True)
    t.start()

    return {"ok": True, "facts": stance.facts, "facts_organizing": True}


async def _organize_facts(debate_id: str, party_id: str) -> None:
    """异步执行 LLM 事实整理，完成后更新 stance 并推送 SSE。"""
    try:
        from services.fact_organizer import organize_facts
        organized = await organize_facts(debate_id, party_id)

        stance = debate_store.get_stance(debate_id, party_id)
        if stance:
            stance.facts = organized
            stance.facts_organizing = False
            stance.updated_at = datetime.now(timezone.utc)
            debate_store.save_stance(stance)
    except Exception as e:
        # 整理失败，解除锁定
        stance = debate_store.get_stance(debate_id, party_id)
        if stance:
            stance.facts_organizing = False
            stance.updated_at = datetime.now(timezone.utc)
            debate_store.save_stance(stance)
        print(f"[fact_organizer] error: {e}")

    # 推送 SSE 事件
    try:
        from routers.stream import push_event
        await push_event(debate_id, "facts_organized", {"party_id": party_id})
    except Exception:
        pass
