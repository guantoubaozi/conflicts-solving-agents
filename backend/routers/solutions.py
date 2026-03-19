"""
routers/solutions.py — 解决方案与裁判梳理接口
"""

import asyncio
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import debate_store
from models.debate import DebateStatus
from models.debate_round import RoundPhase
from models.solution import Solution

router = APIRouter(prefix="/api/debates", tags=["solutions"])


class SolutionIn(BaseModel):
    party_id: str
    content: str


@router.post("/{debate_id}/rounds/{round}/solutions")
def submit_solution(debate_id: str, round: int, body: SolutionIn):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.status != DebateStatus.ROUND:
        raise HTTPException(status_code=400, detail=f"debate is not in ROUND status")
    if debate.current_round != round:
        raise HTTPException(status_code=400, detail=f"current round is {debate.current_round}, not {round}")

    round_state = debate_store.get_round_state(debate_id, round)
    if not round_state or round_state.status != RoundPhase.SOLUTION:
        raise HTTPException(status_code=400, detail="round is not in SOLUTION phase")

    party = debate_store.get_party(debate_id, body.party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")

    solution = Solution(
        solution_id=str(uuid.uuid4()),
        debate_id=debate_id,
        party_id=body.party_id,
        round=round,
        content=body.content,
        created_at=datetime.now(timezone.utc),
    )
    debate_store.save_solution(solution)
    return solution.model_dump(mode="json")


@router.get("/{debate_id}/rounds/{round}/solutions")
def get_solutions(debate_id: str, round: int):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    solutions = debate_store.get_round_solutions(debate_id, round)
    return [s.model_dump(mode="json") for s in solutions]


@router.get("/{debate_id}/rounds/{round}/judge-summary")
def get_judge_summary(debate_id: str, round: int):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    summary = debate_store.get_judge_summary(debate_id, round)
    if not summary:
        raise HTTPException(status_code=404, detail="judge summary not found")
    return summary.model_dump(mode="json")


@router.post("/{debate_id}/rounds/{round}/confirm")
def confirm_round(debate_id: str, round: int, party_id: str):
    """人工确认本轮结束，全员确认后推进下一轮。"""
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.current_round != round:
        raise HTTPException(status_code=400, detail=f"current round is {debate.current_round}")

    round_state = debate_store.get_round_state(debate_id, round)
    if not round_state or round_state.status != RoundPhase.HUMAN_REVIEW:
        raise HTTPException(status_code=400, detail="round is not in HUMAN_REVIEW phase")

    party = debate_store.get_party(debate_id, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")

    if party_id not in round_state.human_confirmed:
        round_state.human_confirmed.append(party_id)
        debate_store.save_round_state(round_state)

    parties = debate_store.get_parties(debate_id)
    all_confirmed = all(p.party_id in round_state.human_confirmed for p in parties)

    if all_confirmed:
        from datetime import datetime, timezone
        round_state.status = RoundPhase.DONE
        round_state.completed_at = datetime.now(timezone.utc)
        debate_store.save_round_state(round_state)

        # 检查是否进入终论
        judge_summary = debate_store.get_judge_summary(debate_id, round)
        if judge_summary and not judge_summary.has_contradiction:
            debate.status = DebateStatus.FINAL
        elif round >= 5:
            debate.status = DebateStatus.FINAL
        else:
            debate.current_round = round + 1
            debate_store.init_round(debate_id, round + 1)

        debate.updated_at = datetime.now(timezone.utc)
        debate_store.save_debate(debate)

    return {
        "confirmed": round_state.human_confirmed,
        "all_confirmed": all_confirmed,
        "debate_status": debate.status,
    }


# ── AI 阶段触发接口 ────────────────────────────────────────

def _run_async(coro):
    """在后台线程中运行异步任务。"""
    import threading
    def _target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
    t = threading.Thread(target=_target, daemon=True)
    t.start()


@router.post("/{debate_id}/rounds/{round}/run-solution")
def trigger_solution_phase(debate_id: str, round: int):
    """触发 AI 生成本轮各方解决方案（后台异步执行）。"""
    from services.debate_service import run_solution_phase
    round_state = debate_store.get_round_state(debate_id, round)
    if not round_state or round_state.status != RoundPhase.SOLUTION:
        raise HTTPException(status_code=400, detail=f"round phase is {round_state.status if round_state else 'N/A'}, expected SOLUTION")

    # 幂等性检查：如果本轮已有解决方案，说明已经触发过，直接返回
    existing = debate_store.get_round_solutions(debate_id, round)
    if existing:
        raise HTTPException(status_code=409, detail="solutions already generated for this round")

    # 防重复触发：如果 AI 正在运行，直接返回
    if round_state.ai_running:
        return {"ok": True, "message": "solution phase already running"}

    # 标记 AI 正在运行
    round_state.ai_running = True
    debate_store.save_round_state(round_state)

    _run_async(run_solution_phase(debate_id, round))
    return {"ok": True, "message": "solution phase started"}


@router.post("/{debate_id}/rounds/{round}/run-judge")
def trigger_judge_phase(debate_id: str, round: int):
    """触发裁判 AI 梳理本轮方案（后台异步执行）。"""
    from services.debate_service import run_judge_phase
    round_state = debate_store.get_round_state(debate_id, round)
    if not round_state or round_state.status != RoundPhase.JUDGE:
        raise HTTPException(status_code=400, detail=f"round phase is {round_state.status if round_state else 'N/A'}, expected JUDGE")

    # 幂等性检查：如果本轮已有裁判梳理结果，说明已经触发过
    existing = debate_store.get_judge_summary(debate_id, round)
    if existing:
        raise HTTPException(status_code=409, detail="judge summary already generated for this round")

    # 防重复触发：如果 AI 正在运行，直接返回
    if round_state.ai_running:
        return {"ok": True, "message": "judge phase already running"}

    # 标记 AI 正在运行
    round_state.ai_running = True
    debate_store.save_round_state(round_state)

    _run_async(run_judge_phase(debate_id, round))
    return {"ok": True, "message": "judge phase started"}


@router.post("/{debate_id}/rounds/{round}/run-debate")
def trigger_debate_phase(debate_id: str, round: int):
    """触发 AI 执行本轮挑战与反思（后台异步执行）。"""
    from services.debate_service import run_debate_phase
    round_state = debate_store.get_round_state(debate_id, round)
    if not round_state or round_state.status != RoundPhase.DEBATE:
        raise HTTPException(status_code=400, detail=f"round phase is {round_state.status if round_state else 'N/A'}, expected DEBATE")

    # 防重复触发：如果 AI 正在运行，直接返回
    if round_state.ai_running:
        return {"ok": True, "message": "debate phase already running"}

    # 标记 AI 正在运行
    round_state.ai_running = True
    debate_store.save_round_state(round_state)

    _run_async(run_debate_phase(debate_id, round))
    return {"ok": True, "message": "debate phase started"}


# ── T6: 直接终论申请 ────────────────────────────────────────

class RequestFinalIn(BaseModel):
    party_id: str


class VoteFinalIn(BaseModel):
    party_id: str
    agree: bool


@router.post("/{debate_id}/rounds/{round}/request-final")
def request_final(debate_id: str, round: int, body: RequestFinalIn):
    """发起直接终论申请，发起方自动算同意。"""
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.current_round != round:
        raise HTTPException(status_code=400, detail=f"current round is {debate.current_round}")

    round_state = debate_store.get_round_state(debate_id, round)
    if not round_state or round_state.status != RoundPhase.HUMAN_REVIEW:
        raise HTTPException(status_code=400, detail="can only request final during HUMAN_REVIEW phase")

    if round_state.final_request_by is not None:
        raise HTTPException(status_code=409, detail="a final request already exists this round")

    party = debate_store.get_party(debate_id, body.party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")

    # 设置申请，发起方自动同意
    round_state.final_request_by = body.party_id
    round_state.final_request_votes = {body.party_id: True}
    debate_store.save_round_state(round_state)

    # 检查是否立即达到阈值（2方辩论且只有发起方时不会，但检查一下）
    parties = debate_store.get_parties(debate_id)
    triggered = _check_final_threshold(debate_id, round, round_state, parties)

    # 推送 SSE
    _run_async(_push_final_vote_update(debate_id, round, round_state))

    return {
        "final_request_by": round_state.final_request_by,
        "final_request_votes": round_state.final_request_votes,
        "final_triggered": triggered,
    }


@router.post("/{debate_id}/rounds/{round}/vote-final")
def vote_final(debate_id: str, round: int, body: VoteFinalIn):
    """对终论申请投票。"""
    debate = debate_store.get_debate(debate_id)
    if not debate:
        raise HTTPException(status_code=404, detail="debate not found")
    if debate.current_round != round:
        raise HTTPException(status_code=400, detail=f"current round is {debate.current_round}")

    round_state = debate_store.get_round_state(debate_id, round)
    if not round_state or round_state.status != RoundPhase.HUMAN_REVIEW:
        raise HTTPException(status_code=400, detail="not in HUMAN_REVIEW phase")

    if round_state.final_request_by is None:
        raise HTTPException(status_code=400, detail="no final request exists")

    party = debate_store.get_party(debate_id, body.party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")

    if body.party_id == round_state.final_request_by:
        raise HTTPException(status_code=400, detail="requester cannot vote again")

    # 记录投票
    round_state.final_request_votes[body.party_id] = body.agree
    debate_store.save_round_state(round_state)

    # 检查阈值
    parties = debate_store.get_parties(debate_id)
    triggered = _check_final_threshold(debate_id, round, round_state, parties)

    # 推送 SSE
    _run_async(_push_final_vote_update(debate_id, round, round_state))

    return {
        "final_request_by": round_state.final_request_by,
        "final_request_votes": round_state.final_request_votes,
        "final_triggered": triggered,
    }


def _check_final_threshold(debate_id: str, round_num: int, round_state, parties) -> bool:
    """检查终论投票是否达到阈值，达到则触发终论流程。"""
    total = len(parties)
    votes = round_state.final_request_votes
    agree_count = sum(1 for v in votes.values() if v)

    if total == 2:
        # 2方：需全部同意
        threshold_met = agree_count == total
    else:
        # ≥3方：需 >50% 同意
        threshold_met = agree_count > total / 2

    # 还需要所有人都投过票才能判定（除非已达到阈值）
    all_voted = len(votes) == total

    if threshold_met:
        # 触发终论
        from services.debate_service import _run_final_no_contradiction
        from agents.judge_agent import JudgeAgent
        judge = JudgeAgent(debate_id)
        _run_async(_run_final_no_contradiction(debate_id, round_num, judge))
        return True

    if all_voted and not threshold_met:
        # 所有人投完但未达阈值，申请失败，清除状态
        round_state.final_request_by = None
        round_state.final_request_votes = {}
        debate_store.save_round_state(round_state)

    return False


async def _push_final_vote_update(debate_id: str, round_num: int, round_state) -> None:
    """推送终论投票状态更新 SSE。"""
    try:
        from routers.stream import push_event
        await push_event(debate_id, "final_vote_update", {
            "round": round_num,
            "final_request_by": round_state.final_request_by,
            "final_request_votes": round_state.final_request_votes,
        })
    except Exception:
        pass
