"""
services/debate_service.py — 辩论流程编排

辩论状态机：INIT → STANCE → ROUND(1-5) → FINAL
每轮阶段流转：SOLUTION → JUDGE → DEBATE → HUMAN_REVIEW → DONE

服务启动时扫描 debates/ 目录，恢复未完成的辩论场次。
SSE 事件通过 routers/stream.py 的 push_event 推送。
"""

import asyncio
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import storage, debate_store
from services.evidence_compressor import check_and_mark_pending, run_pending_compressions
from models.debate import DebateStatus
from models.debate_round import RoundPhase
from agents.party_agent import PartyAgent
from agents.judge_agent import JudgeAgent

MAX_ROUNDS = 5


def _active_parties_for_round(debate_id: str, round_num: int):
    """
    返回本轮可参与辩论的辩论方列表：
    - joined_round < round_num（初始加入方 joined_round=0，满足 0 < 1）
    - 已提交立论
    """
    parties = debate_store.get_parties(debate_id)
    result = []
    for p in parties:
        if p.joined_round >= round_num:
            continue  # 本轮或之后加入，等下一轮
        if not debate_store.get_stance(debate_id, p.party_id):
            continue  # 未提交立论
        result.append(p)
    return result


async def _push(debate_id: str, event_type: str, data: dict) -> None:
    """推送 SSE 事件（延迟导入避免循环依赖）。"""
    try:
        from routers.stream import push_event
        await push_event(debate_id, event_type, data)
    except Exception:
        pass


async def _wait_facts_organized(debate_id: str, party_id: str, timeout: int = 60) -> None:
    """等待指定方的事实整理完成，最多等 timeout 秒。"""
    import time
    start = time.time()
    while time.time() - start < timeout:
        stance = debate_store.get_stance(debate_id, party_id)
        if not stance or not stance.facts_organizing:
            return
        await asyncio.sleep(2)
    # 超时后强制解除锁定
    stance = debate_store.get_stance(debate_id, party_id)
    if stance and stance.facts_organizing:
        from datetime import datetime, timezone
        stance.facts_organizing = False
        stance.updated_at = datetime.now(timezone.utc)
        debate_store.save_stance(stance)


# ── 阶段推进 ──────────────────────────────────────────────

async def run_solution_phase(debate_id: str, round_num: int) -> None:
    """
    SOLUTION 阶段：各辩论方 Agent 生成解决方案。
    论据压缩检查在 PartyAgent._wait_evidence_ready 内部处理。
    """
    debate = debate_store.get_debate(debate_id)
    if not debate or debate.status != DebateStatus.ROUND:
        return

    round_state = debate_store.get_round_state(debate_id, round_num)
    if not round_state or round_state.status != RoundPhase.SOLUTION:
        return

    parties = _active_parties_for_round(debate_id, round_num)
    try:
        for party in parties:
            # 幂等性检查：跳过已有解决方案的辩论方
            if debate_store.get_solution(debate_id, round_num, party.party_id):
                continue

            # 等待事实整理完成（T4）
            await _wait_facts_organized(debate_id, party.party_id)

            # 先触发论据压缩检查
            check_and_mark_pending(debate_id, party.party_id)
            await run_pending_compressions(debate_id, party.party_id)

            await _push(debate_id, "agent_start", {
                "agent": f"party_{party.party_id}",
                "phase": "solution",
                "round": round_num,
            })

            agent = PartyAgent(debate_id, party.party_id)
            output = agent.generate_solution(round_num)

            await _push(debate_id, "agent_done", {
                "agent": f"party_{party.party_id}",
                "phase": "solution",
                "round": round_num,
                "summary": output[:200],
            })

        # 推进到 JUDGE 阶段，自动触发裁判梳理
        round_state.status = RoundPhase.JUDGE
        debate_store.save_round_state(round_state)
        await _push(debate_id, "round_phase_change", {"round": round_num, "phase": "JUDGE"})

        # 自动链式执行裁判梳理（ai_running 保持 True）
        await run_judge_phase(debate_id, round_num)
    except Exception:
        # 出错时重置 ai_running，允许用户重试
        round_state = debate_store.get_round_state(debate_id, round_num)
        if round_state:
            round_state.ai_running = False
            debate_store.save_round_state(round_state)
        raise


async def run_judge_phase(debate_id: str, round_num: int) -> None:
    """JUDGE 阶段：裁判 Agent 梳理各方方案。"""
    round_state = debate_store.get_round_state(debate_id, round_num)
    if not round_state or round_state.status != RoundPhase.JUDGE:
        return

    await _push(debate_id, "agent_start", {"agent": "judge", "phase": "judge", "round": round_num})

    try:
        judge = JudgeAgent(debate_id)
        output = judge.run_round_review(round_num)

        await _push(debate_id, "agent_done", {"agent": "judge", "phase": "judge", "round": round_num, "summary": output[:200]})

        # 检查是否触发终论
        summary = debate_store.get_judge_summary(debate_id, round_num)
        debate = debate_store.get_debate(debate_id)

        if summary and not summary.has_contradiction:
            # 无矛盾 → 终论
            round_state.ai_running = False
            debate_store.save_round_state(round_state)
            await _run_final_no_contradiction(debate_id, round_num, judge)
            return

        if round_num >= MAX_ROUNDS:
            # 满 5 轮 → 终论
            round_state.ai_running = False
            debate_store.save_round_state(round_state)
            await _run_final_max_rounds(debate_id, round_num, judge)
            return

        # 推进到 DEBATE 阶段
        round_state.status = RoundPhase.DEBATE
        round_state.ai_running = False
        debate_store.save_round_state(round_state)
        await _push(debate_id, "round_phase_change", {"round": round_num, "phase": "DEBATE"})
    except Exception:
        round_state = debate_store.get_round_state(debate_id, round_num)
        if round_state:
            round_state.ai_running = False
            debate_store.save_round_state(round_state)
        raise


async def run_debate_phase(debate_id: str, round_num: int) -> None:
    """DEBATE 阶段：各方执行挑战和反思。"""
    round_state = debate_store.get_round_state(debate_id, round_num)
    if not round_state or round_state.status != RoundPhase.DEBATE:
        return

    parties = _active_parties_for_round(debate_id, round_num)
    party_ids = [p.party_id for p in parties]

    try:
        # 挑战阶段：各方生成挑战
        for party in parties:
            await _push(debate_id, "agent_start", {"agent": f"party_{party.party_id}", "phase": "challenge", "round": round_num})
            agent = PartyAgent(debate_id, party.party_id)
            output = agent.generate_challenge(round_num)
            await _push(debate_id, "agent_done", {"agent": f"party_{party.party_id}", "phase": "challenge", "round": round_num, "summary": output[:200]})

        # 反思阶段：各方读取对方挑战并反思
        for party in parties:
            challengers = [pid for pid in party_ids if pid != party.party_id]
            await _push(debate_id, "agent_start", {"agent": f"party_{party.party_id}", "phase": "reflection", "round": round_num})
            agent = PartyAgent(debate_id, party.party_id)
            output = agent.generate_reflection(round_num, challengers)
            await _push(debate_id, "agent_done", {"agent": f"party_{party.party_id}", "phase": "reflection", "round": round_num, "summary": output[:200]})

        # 推进到 HUMAN_REVIEW 阶段
        round_state.status = RoundPhase.HUMAN_REVIEW
        round_state.ai_running = False
        debate_store.save_round_state(round_state)
        await _push(debate_id, "round_phase_change", {"round": round_num, "phase": "HUMAN_REVIEW"})
    except Exception:
        round_state = debate_store.get_round_state(debate_id, round_num)
        if round_state:
            round_state.ai_running = False
            debate_store.save_round_state(round_state)
        raise


async def _run_final_no_contradiction(debate_id: str, round_num: int, judge: JudgeAgent) -> None:
    """无矛盾终论。"""
    from datetime import datetime, timezone
    await _push(debate_id, "agent_start", {"agent": "judge", "phase": "final", "round": round_num})
    judge.run_final_verdict_no_contradiction(round_num)
    await _push(debate_id, "agent_done", {"agent": "judge", "phase": "final"})

    debate = debate_store.get_debate(debate_id)
    debate.status = DebateStatus.FINAL
    debate.updated_at = datetime.now(timezone.utc)
    debate_store.save_debate(debate)
    await _push(debate_id, "debate_final", {"reason": "no_contradiction", "round": round_num})


async def _run_final_max_rounds(debate_id: str, round_num: int, judge: JudgeAgent) -> None:
    """满 5 轮终论：各方再提交一轮最终方案，裁判选出最简单/代价最小的方案。"""
    from datetime import datetime, timezone

    # 各方提交最终方案
    parties = debate_store.get_parties(debate_id)
    for party in parties:
        check_and_mark_pending(debate_id, party.party_id)
        await run_pending_compressions(debate_id, party.party_id)
        await _push(debate_id, "agent_start", {"agent": f"party_{party.party_id}", "phase": "final_solution"})
        agent = PartyAgent(debate_id, party.party_id)
        agent.generate_solution(round_num)
        await _push(debate_id, "agent_done", {"agent": f"party_{party.party_id}", "phase": "final_solution"})

    # 裁判终论裁决
    await _push(debate_id, "agent_start", {"agent": "judge", "phase": "final_verdict"})
    judge.run_final_verdict_max_rounds(round_num)
    await _push(debate_id, "agent_done", {"agent": "judge", "phase": "final_verdict"})

    debate = debate_store.get_debate(debate_id)
    debate.status = DebateStatus.FINAL
    debate.updated_at = datetime.now(timezone.utc)
    debate_store.save_debate(debate)
    await _push(debate_id, "debate_final", {"reason": "max_rounds", "round": round_num})


# ── 服务启动恢复 ───────────────────────────────────────────

def recover_debates() -> list[str]:
    """
    服务启动时扫描 debates/ 目录，返回所有未完成的 debate_id 列表。
    调用方可根据需要决定是否自动恢复（继续执行中断的阶段）。
    """
    unfinished = []
    for debate_id in storage.list_debate_ids():
        debate = debate_store.get_debate(debate_id)
        if debate and debate.status != DebateStatus.FINAL:
            unfinished.append(debate_id)
    return unfinished


def get_current_phase(debate_id: str) -> dict:
    """返回当前辩论的阶段信息，用于重启后恢复。"""
    debate = debate_store.get_debate(debate_id)
    if not debate:
        return {}

    result = {
        "debate_id": debate_id,
        "status": debate.status,
        "current_round": debate.current_round,
    }

    if debate.status == DebateStatus.ROUND:
        round_state = debate_store.get_round_state(debate_id, debate.current_round)
        if round_state:
            result["round_phase"] = round_state.status
            result["human_confirmed"] = round_state.human_confirmed

    return result
