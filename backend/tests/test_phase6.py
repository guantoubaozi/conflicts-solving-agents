"""
阶段六单元测试：辩论流程编排
"""

import asyncio
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import services.storage as storage
import services.debate_store as debate_store
import config as cfg
from models.debate import DebateStatus
from models.debate_round import RoundPhase
from models.judge_summary import JudgeSummary


def _setup(tmp: str):
    storage._BASE = Path(tmp) / "debates"
    cfg._CONFIG_PATH = Path(tmp) / "config.json"
    cfg.write_config("https://api.test.com", "sk-test")


def _create_debate_with_parties(debate_id_override: str = None) -> tuple[str, list[str]]:
    """创建辩论并添加两个已提交立论的辩论方，返回 (debate_id, [party_id_a, party_id_b])。"""
    debate, _ = debate_store.create_debate("测试命题", "tester")
    debate_id = debate.debate_id

    party_a = debate_store.add_party(debate_id, "甲方", joined_round=0)
    party_b = debate_store.add_party(debate_id, "乙方", joined_round=0)

    # 提交立论
    from models.stance import Stance
    now = datetime.now(timezone.utc)
    for pid in [party_a.party_id, party_b.party_id]:
        stance = Stance(
            stance_id=str(uuid.uuid4()),
            party_id=pid,
            debate_id=debate_id,
            viewpoint="我方观点",
            facts="",
            evidence_pool=[],
            created_at=now,
            updated_at=now,
        )
        debate_store.save_stance(stance)

    # 推进到 ROUND 状态
    debate.status = DebateStatus.ROUND
    debate.updated_at = now
    debate_store.save_debate(debate)
    debate_store.init_round(debate_id, 1)

    return debate_id, [party_a.party_id, party_b.party_id]


def _make_judge_summary(debate_id: str, round_num: int, has_contradiction: bool) -> JudgeSummary:
    summary = JudgeSummary(
        summary_id=str(uuid.uuid4()),
        debate_id=debate_id,
        round=round_num,
        consensus="共识内容",
        contradictions="矛盾内容" if has_contradiction else "",
        combined_solution="综合方案",
        has_contradiction=has_contradiction,
        created_at=datetime.now(timezone.utc),
    )
    debate_store.save_judge_summary(summary)
    return summary


# ── 测试 1：状态机合法流转 ─────────────────────────────────

def test_state_machine_legal_transitions():
    """SOLUTION → JUDGE → DEBATE → HUMAN_REVIEW 合法流转。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_ids = _create_debate_with_parties()

        from services import debate_service

        with patch("services.debate_service.PartyAgent") as MockParty, \
             patch("services.debate_service.JudgeAgent") as MockJudge, \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):

            mock_party_inst = MagicMock()
            mock_party_inst.generate_solution.return_value = "解决方案内容"
            MockParty.return_value = mock_party_inst

            mock_judge_inst = MagicMock()
            mock_judge_inst.run_round_review.return_value = "裁判梳理内容"
            MockJudge.return_value = mock_judge_inst

            # SOLUTION 阶段
            round_state = debate_store.get_round_state(debate_id, 1)
            assert round_state.status == RoundPhase.SOLUTION

            asyncio.run(debate_service.run_solution_phase(debate_id, 1))
            round_state = debate_store.get_round_state(debate_id, 1)
            assert round_state.status == RoundPhase.JUDGE, f"期望 JUDGE，实际 {round_state.status}"

            # JUDGE 阶段（有矛盾，继续辩论）
            _make_judge_summary(debate_id, 1, has_contradiction=True)
            asyncio.run(debate_service.run_judge_phase(debate_id, 1))
            round_state = debate_store.get_round_state(debate_id, 1)
            assert round_state.status == RoundPhase.DEBATE, f"期望 DEBATE，实际 {round_state.status}"

            # DEBATE 阶段
            mock_party_inst.generate_challenge.return_value = "挑战内容"
            mock_party_inst.generate_reflection.return_value = "反思内容"
            asyncio.run(debate_service.run_debate_phase(debate_id, 1))
            round_state = debate_store.get_round_state(debate_id, 1)
            assert round_state.status == RoundPhase.HUMAN_REVIEW, f"期望 HUMAN_REVIEW，实际 {round_state.status}"

    print("PASS: state_machine_legal_transitions")


# ── 测试 2：非法状态转换被拒绝 ────────────────────────────

def test_state_machine_illegal_transitions():
    """非法状态转换（如在 JUDGE 阶段调用 run_solution_phase）被拒绝（无副作用）。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_ids = _create_debate_with_parties()

        from services import debate_service

        with patch("services.debate_service.PartyAgent") as MockParty, \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):

            mock_party_inst = MagicMock()
            mock_party_inst.generate_solution.return_value = "方案"
            MockParty.return_value = mock_party_inst

            # 先正常推进到 JUDGE
            asyncio.run(debate_service.run_solution_phase(debate_id, 1))
            round_state = debate_store.get_round_state(debate_id, 1)
            assert round_state.status == RoundPhase.JUDGE

            # 再次调用 run_solution_phase（当前是 JUDGE 阶段），应无副作用
            asyncio.run(debate_service.run_solution_phase(debate_id, 1))
            round_state = debate_store.get_round_state(debate_id, 1)
            assert round_state.status == RoundPhase.JUDGE, "非法调用不应改变状态"

    print("PASS: state_machine_illegal_transitions")


# ── 测试 3：轮次上限 ──────────────────────────────────────

def test_max_rounds_triggers_final():
    """第 5 轮 JUDGE 阶段（有矛盾）后自动进入 FINAL，不开启第 6 轮。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_ids = _create_debate_with_parties()

        # 手动将辩论推进到第 5 轮
        debate = debate_store.get_debate(debate_id)
        debate.current_round = 5
        debate_store.save_debate(debate)
        debate_store.init_round(debate_id, 5)

        # 设置第 5 轮为 JUDGE 阶段
        round_state = debate_store.get_round_state(debate_id, 5)
        round_state.status = RoundPhase.JUDGE
        debate_store.save_round_state(round_state)

        from services import debate_service

        with patch("services.debate_service.JudgeAgent") as MockJudge, \
             patch("services.debate_service.PartyAgent") as MockParty, \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):

            mock_judge_inst = MagicMock()
            mock_judge_inst.run_round_review.return_value = "裁判梳理"
            mock_judge_inst.run_final_verdict_max_rounds.return_value = "终论裁决"
            MockJudge.return_value = mock_judge_inst

            mock_party_inst = MagicMock()
            mock_party_inst.generate_solution.return_value = "最终方案"
            MockParty.return_value = mock_party_inst

            _make_judge_summary(debate_id, 5, has_contradiction=True)
            asyncio.run(debate_service.run_judge_phase(debate_id, 5))

        debate = debate_store.get_debate(debate_id)
        assert debate.status == DebateStatus.FINAL, f"期望 FINAL，实际 {debate.status}"
        assert debate.current_round == 5, "轮次不应超过 5"

    print("PASS: max_rounds_triggers_final")


# ── 测试 4：无矛盾时直接进入终论 ─────────────────────────

def test_no_contradiction_triggers_final():
    """JUDGE 阶段无矛盾时直接进入 FINAL。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_ids = _create_debate_with_parties()

        round_state = debate_store.get_round_state(debate_id, 1)
        round_state.status = RoundPhase.JUDGE
        debate_store.save_round_state(round_state)

        from services import debate_service

        with patch("services.debate_service.JudgeAgent") as MockJudge:
            mock_judge_inst = MagicMock()
            mock_judge_inst.run_round_review.return_value = "裁判梳理"
            mock_judge_inst.run_final_verdict_no_contradiction.return_value = "终论"
            MockJudge.return_value = mock_judge_inst

            _make_judge_summary(debate_id, 1, has_contradiction=False)
            asyncio.run(debate_service.run_judge_phase(debate_id, 1))

        debate = debate_store.get_debate(debate_id)
        assert debate.status == DebateStatus.FINAL, f"期望 FINAL，实际 {debate.status}"

    print("PASS: no_contradiction_triggers_final")


# ── 测试 5：中途加入辩论方 ────────────────────────────────

def test_mid_debate_join():
    """
    在第 1 轮 SOLUTION 阶段加入第 3 方（joined_round=1），
    该方不参与第 1 轮，提交立论后参与第 2 轮。
    """
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_ids = _create_debate_with_parties()

        # 在第 1 轮加入第 3 方（未提交立论）
        party_c = debate_store.add_party(debate_id, "丙方", joined_round=1)

        from services import debate_service

        called_parties = []

        def mock_generate_solution(round_num):
            called_parties.append(round_num)
            return "方案"

        with patch("services.debate_service.PartyAgent") as MockParty, \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):

            mock_party_inst = MagicMock()
            mock_party_inst.generate_solution.side_effect = mock_generate_solution
            MockParty.return_value = mock_party_inst

            asyncio.run(debate_service.run_solution_phase(debate_id, 1))

        # 第 1 轮只有 2 方参与（甲方、乙方），丙方未提交立论且 joined_round=1
        assert len(called_parties) == 2, f"第 1 轮应有 2 方参与，实际 {len(called_parties)}"

        # 丙方提交立论
        from models.stance import Stance
        now = datetime.now(timezone.utc)
        stance_c = Stance(
            stance_id=str(uuid.uuid4()),
            party_id=party_c.party_id,
            debate_id=debate_id,
            viewpoint="丙方观点",
            facts="",
            evidence_pool=[],
            created_at=now,
            updated_at=now,
        )
        debate_store.save_stance(stance_c)

        # 推进到第 2 轮
        debate = debate_store.get_debate(debate_id)
        debate.current_round = 2
        debate_store.save_debate(debate)
        debate_store.init_round(debate_id, 2)

        called_parties.clear()

        with patch("services.debate_service.PartyAgent") as MockParty2, \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):

            mock_party_inst2 = MagicMock()
            mock_party_inst2.generate_solution.side_effect = mock_generate_solution
            MockParty2.return_value = mock_party_inst2

            asyncio.run(debate_service.run_solution_phase(debate_id, 2))

        # 第 2 轮 3 方都参与（joined_round=1 < round_num=2）
        assert len(called_parties) == 3, f"第 2 轮应有 3 方参与，实际 {len(called_parties)}"

    print("PASS: mid_debate_join")


# ── 测试 6：服务重启恢复 ──────────────────────────────────

def test_restart_recovery():
    """服务重启后 recover_debates() 返回未完成的辩论，get_current_phase() 返回正确阶段。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_ids = _create_debate_with_parties()

        # 模拟中断：辩论在第 2 轮 HUMAN_REVIEW 阶段
        debate = debate_store.get_debate(debate_id)
        debate.current_round = 2
        debate_store.save_debate(debate)
        debate_store.init_round(debate_id, 2)
        round_state = debate_store.get_round_state(debate_id, 2)
        round_state.status = RoundPhase.HUMAN_REVIEW
        round_state.human_confirmed = [party_ids[0]]
        debate_store.save_round_state(round_state)

        from services.debate_service import recover_debates, get_current_phase

        unfinished = recover_debates()
        assert debate_id in unfinished, f"应包含未完成的 {debate_id}"

        phase_info = get_current_phase(debate_id)
        assert phase_info["status"] == DebateStatus.ROUND
        assert phase_info["current_round"] == 2
        assert phase_info["round_phase"] == RoundPhase.HUMAN_REVIEW
        assert party_ids[0] in phase_info["human_confirmed"]

        # 已完成的辩论不应出现在 unfinished 中
        debate.status = DebateStatus.FINAL
        debate_store.save_debate(debate)
        unfinished2 = recover_debates()
        assert debate_id not in unfinished2

    print("PASS: restart_recovery")


# ── 测试 7：SSE 事件推送 ──────────────────────────────────

def test_sse_events_pushed():
    """各阶段触发时对应 SSE 事件被推送，事件类型和字段正确。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_ids = _create_debate_with_parties()

        pushed_events = []

        async def fake_push(did, event_type, data):
            pushed_events.append({"type": event_type, "data": data})

        from services import debate_service

        with patch.object(debate_service, "_push", side_effect=fake_push), \
             patch("services.debate_service.PartyAgent") as MockParty, \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):

            mock_party_inst = MagicMock()
            mock_party_inst.generate_solution.return_value = "方案"
            MockParty.return_value = mock_party_inst

            asyncio.run(debate_service.run_solution_phase(debate_id, 1))

        event_types = [e["type"] for e in pushed_events]
        assert "agent_start" in event_types, "应有 agent_start 事件"
        assert "agent_done" in event_types, "应有 agent_done 事件"
        assert "round_phase_change" in event_types, "应有 round_phase_change 事件"

        phase_change = next(e for e in pushed_events if e["type"] == "round_phase_change")
        assert phase_change["data"]["phase"] == "JUDGE"
        assert phase_change["data"]["round"] == 1

    print("PASS: sse_events_pushed")


if __name__ == "__main__":
    test_state_machine_legal_transitions()
    test_state_machine_illegal_transitions()
    test_max_rounds_triggers_final()
    test_no_contradiction_triggers_final()
    test_mid_debate_join()
    test_restart_recovery()
    test_sse_events_pushed()
    print("\n所有阶段六测试通过。")
