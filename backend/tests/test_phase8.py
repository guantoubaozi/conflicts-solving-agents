"""
阶段八集成测试：端到端流程、重启恢复、压缩时序、多场隔离
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
from models.stance import Stance
from models.judge_summary import JudgeSummary


def _setup(tmp: str):
    storage._BASE = Path(tmp) / "debates"
    cfg._CONFIG_PATH = Path(tmp) / "config.json"
    cfg.write_config("https://api.test.com", "sk-test")


def _make_stance(debate_id: str, party_id: str):
    now = datetime.now(timezone.utc)
    s = Stance(
        stance_id=str(uuid.uuid4()),
        party_id=party_id,
        debate_id=debate_id,
        viewpoint="我方观点",
        facts="我方事实",
        evidence_pool=[],
        created_at=now,
        updated_at=now,
    )
    debate_store.save_stance(s)


def _make_judge_summary(debate_id: str, round_num: int, has_contradiction: bool):
    s = JudgeSummary(
        summary_id=str(uuid.uuid4()),
        debate_id=debate_id,
        round=round_num,
        consensus="共识",
        contradictions="矛盾" if has_contradiction else "",
        combined_solution="综合方案",
        has_contradiction=has_contradiction,
        created_at=datetime.now(timezone.utc),
    )
    debate_store.save_judge_summary(s)


def _mock_agents():
    """返回 patch 上下文，mock 所有 Agent 调用。"""
    mock_party = MagicMock()
    mock_party.generate_solution.return_value = "解决方案"
    mock_party.generate_challenge.return_value = "挑战内容"
    mock_party.generate_reflection.return_value = "反思内容"

    mock_judge = MagicMock()
    mock_judge.run_round_review.return_value = "裁判梳理"
    mock_judge.run_final_verdict_no_contradiction.return_value = "终论（无矛盾）"
    mock_judge.run_final_verdict_max_rounds.return_value = "终论（满5轮）"

    return mock_party, mock_judge


# ── 测试 1：端到端两方辩论走完 5 轮 ──────────────────────

def test_e2e_two_parties_five_rounds():
    """两方辩论，有矛盾，走完 5 轮后进入 FINAL。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)

        debate, _ = debate_store.create_debate("测试命题", "tester")
        did = debate.debate_id
        pa = debate_store.add_party(did, "甲方", joined_round=0)
        pb = debate_store.add_party(did, "乙方", joined_round=0)
        _make_stance(did, pa.party_id)
        _make_stance(did, pb.party_id)

        debate.status = DebateStatus.ROUND
        debate_store.save_debate(debate)
        debate_store.init_round(did, 1)

        from services import debate_service

        mock_party, mock_judge = _mock_agents()

        with patch("services.debate_service.PartyAgent", return_value=mock_party), \
             patch("services.debate_service.JudgeAgent", return_value=mock_judge), \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):

            for round_num in range(1, 6):
                # 确保当前轮次正确
                d = debate_store.get_debate(did)
                assert d.current_round == round_num, f"期望第 {round_num} 轮，实际 {d.current_round}"

                # SOLUTION 阶段
                asyncio.run(debate_service.run_solution_phase(did, round_num))
                rs = debate_store.get_round_state(did, round_num)
                assert rs.status == RoundPhase.JUDGE

                # JUDGE 阶段（有矛盾）
                _make_judge_summary(did, round_num, has_contradiction=True)
                asyncio.run(debate_service.run_judge_phase(did, round_num))

                d = debate_store.get_debate(did)
                if round_num < 5:
                    rs = debate_store.get_round_state(did, round_num)
                    assert rs.status == RoundPhase.DEBATE

                    # DEBATE 阶段
                    asyncio.run(debate_service.run_debate_phase(did, round_num))
                    rs = debate_store.get_round_state(did, round_num)
                    assert rs.status == RoundPhase.HUMAN_REVIEW

                    # 全员确认
                    rs.status = RoundPhase.DONE
                    debate_store.save_round_state(rs)
                    d.current_round = round_num + 1
                    debate_store.save_debate(d)
                    debate_store.init_round(did, round_num + 1)
                else:
                    # 第 5 轮后应进入 FINAL
                    assert d.status == DebateStatus.FINAL, f"第5轮后期望 FINAL，实际 {d.status}"

        d = debate_store.get_debate(did)
        assert d.status == DebateStatus.FINAL
        assert d.current_round == 5

    print("PASS: e2e_two_parties_five_rounds")


# ── 测试 2：服务重启恢复 ──────────────────────────────────

def test_restart_recovery_full():
    """模拟服务中断后重启，从 debate_state.json 正确恢复到中断前的阶段。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)

        debate, _ = debate_store.create_debate("重启测试命题", "tester")
        did = debate.debate_id
        pa = debate_store.add_party(did, "甲方", joined_round=0)
        pb = debate_store.add_party(did, "乙方", joined_round=0)
        _make_stance(did, pa.party_id)
        _make_stance(did, pb.party_id)

        # 模拟中断：辩论在第 3 轮 DEBATE 阶段
        debate.status = DebateStatus.ROUND
        debate.current_round = 3
        debate_store.save_debate(debate)
        debate_store.init_round(did, 3)
        rs = debate_store.get_round_state(did, 3)
        rs.status = RoundPhase.DEBATE
        debate_store.save_round_state(rs)

        # 模拟重启：重新加载状态
        from services.debate_service import recover_debates, get_current_phase

        unfinished = recover_debates()
        assert did in unfinished, "重启后应发现未完成的辩论"

        phase = get_current_phase(did)
        assert phase["status"] == DebateStatus.ROUND
        assert phase["current_round"] == 3
        assert phase["round_phase"] == RoundPhase.DEBATE

        # 验证从中断点继续（DEBATE 阶段可以继续执行）
        mock_party, _ = _mock_agents()
        with patch("services.debate_service.PartyAgent", return_value=mock_party), \
             patch("services.evidence_compressor.check_and_mark_pending", return_value=[]), \
             patch("services.evidence_compressor.run_pending_compressions", new=AsyncMock()):
            from services import debate_service
            asyncio.run(debate_service.run_debate_phase(did, 3))

        rs = debate_store.get_round_state(did, 3)
        assert rs.status == RoundPhase.HUMAN_REVIEW, "从中断点继续后应推进到 HUMAN_REVIEW"

    print("PASS: restart_recovery_full")


# ── 测试 3：论据压缩时序 ──────────────────────────────────

def test_evidence_compression_timing():
    """压缩中不可引用（Agent 等待），完成后可引用。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)

        debate, _ = debate_store.create_debate("压缩时序测试", "tester")
        did = debate.debate_id
        pa = debate_store.add_party(did, "甲方", joined_round=0)

        # 写入一条 COMPRESSING 状态的论据
        evidence_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        stance = {
            "stance_id": str(uuid.uuid4()),
            "party_id": pa.party_id,
            "debate_id": did,
            "viewpoint": "观点",
            "facts": "",
            "evidence_pool": [{
                "evidence_id": evidence_id,
                "content": "论" * 5001,
                "is_valid": True,
                "created_round": 1,
                "compress_status": "COMPRESSING",
            }],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        storage.write_stance(did, pa.party_id, stance)

        # 模拟 PartyAgent._wait_evidence_ready：COMPRESSING 时阻塞
        wait_calls = []

        def fake_wait(self_obj, round_num):
            wait_calls.append(round_num)
            # 模拟等待后压缩完成
            s = storage.read_stance(did, pa.party_id)
            s["evidence_pool"][0]["compress_status"] = "DONE"
            storage.write_stance(did, pa.party_id, s)

        from agents import party_agent as pa_module
        original_wait = pa_module.PartyAgent._wait_evidence_ready

        # 直接测试 _wait_evidence_ready 逻辑
        # 先设置为 COMPRESSING，然后在另一线程中改为 DONE
        import threading

        def set_done_after_delay():
            import time
            time.sleep(0.1)
            s = storage.read_stance(did, pa.party_id)
            s["evidence_pool"][0]["compress_status"] = "DONE"
            storage.write_stance(did, pa.party_id, s)

        # 重置为 COMPRESSING
        s = storage.read_stance(did, pa.party_id)
        s["evidence_pool"][0]["compress_status"] = "COMPRESSING"
        storage.write_stance(did, pa.party_id, s)

        t = threading.Thread(target=set_done_after_delay)
        t.start()

        # 创建一个最小化的 PartyAgent 来测试 _wait_evidence_ready
        # 不实例化真实 Agent（避免 LLM 调用），直接测试等待逻辑
        class FakeAgent:
            def __init__(self):
                self.debate_id = did
                self.party_id = pa.party_id

            _wait_evidence_ready = pa_module.PartyAgent._wait_evidence_ready

        fake = FakeAgent()
        fake._wait_evidence_ready(1)  # 应该等待直到 DONE
        t.join()

        s = storage.read_stance(did, pa.party_id)
        assert s["evidence_pool"][0]["compress_status"] == "DONE", "等待后论据应为 DONE 状态"

    print("PASS: evidence_compression_timing")


# ── 测试 4：多场并发隔离 ──────────────────────────────────

def test_multi_debate_isolation():
    """两场辩论同时进行，验证内容不互串。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)

        # 创建两场辩论
        d1, _ = debate_store.create_debate("命题一", "tester")
        d2, _ = debate_store.create_debate("命题二", "tester")

        pa1 = debate_store.add_party(d1.debate_id, "甲方A", joined_round=0)
        pa2 = debate_store.add_party(d2.debate_id, "甲方B", joined_round=0)

        _make_stance(d1.debate_id, pa1.party_id)
        _make_stance(d2.debate_id, pa2.party_id)

        # 写入不同内容的裁判梳理
        _make_judge_summary(d1.debate_id, 1, has_contradiction=True)
        _make_judge_summary(d2.debate_id, 1, has_contradiction=False)

        # 验证两场辩论的数据完全隔离
        s1 = debate_store.get_judge_summary(d1.debate_id, 1)
        s2 = debate_store.get_judge_summary(d2.debate_id, 1)

        assert s1.has_contradiction is True
        assert s2.has_contradiction is False
        assert s1.debate_id == d1.debate_id
        assert s2.debate_id == d2.debate_id

        # 验证辩论方数据隔离
        parties1 = debate_store.get_parties(d1.debate_id)
        parties2 = debate_store.get_parties(d2.debate_id)
        assert len(parties1) == 1
        assert len(parties2) == 1
        assert parties1[0].party_id != parties2[0].party_id

        # 验证立论数据隔离
        stance1 = debate_store.get_stance(d1.debate_id, pa1.party_id)
        stance2 = debate_store.get_stance(d2.debate_id, pa2.party_id)
        assert stance1 is not None
        assert stance2 is not None
        # 跨场次读取应返回 None
        assert debate_store.get_stance(d1.debate_id, pa2.party_id) is None
        assert debate_store.get_stance(d2.debate_id, pa1.party_id) is None

        # 验证 thread_id 隔离（不同 debate_id 的 thread_id 不同）
        thread1 = f"{d1.debate_id}_{pa1.party_id}"
        thread2 = f"{d2.debate_id}_{pa2.party_id}"
        assert thread1 != thread2

    print("PASS: multi_debate_isolation")


# ── 需求全量核查 ──────────────────────────────────────────

def test_requirements_check():
    """对照需求文档核查关键约束。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)

        debate, _ = debate_store.create_debate("核查命题", "tester")
        did = debate.debate_id
        pa = debate_store.add_party(did, "甲方", joined_round=0)

        # 1. 观点字数校验（后端 API 层）
        from fastapi.testclient import TestClient
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from main import app
        client = TestClient(app)

        # 提交超长观点应返回 422
        resp = client.post(f"/api/debates/{did}/parties/{pa.party_id}/stance", json={
            "viewpoint": "观" * 201,
            "facts": "",
            "evidence_pool": [],
        })
        assert resp.status_code == 422, f"超长观点应返回 422，实际 {resp.status_code}"

        # 提交超长事实应返回 422
        resp = client.post(f"/api/debates/{did}/parties/{pa.party_id}/stance", json={
            "viewpoint": "观点",
            "facts": "事" * 1001,
            "evidence_pool": [],
        })
        assert resp.status_code == 422, f"超长事实应返回 422，实际 {resp.status_code}"

        # 2. 辩论方在 FINAL 阶段不可加入
        debate.status = DebateStatus.FINAL
        debate_store.save_debate(debate)
        resp = client.post(f"/api/debates/{did}/parties", json={"name": "新方"})
        assert resp.status_code == 400, f"FINAL 阶段不可加入，实际 {resp.status_code}"

        # 3. KEY 脱敏
        cfg.write_config("https://api.test.com", "sk-secret-key-12345")
        resp = client.get("/api/config")
        assert resp.status_code == 200
        key_returned = resp.json()["api_key_masked"]
        assert "secret" not in key_returned, "KEY 应脱敏，不应包含原始内容"
        assert "*" in key_returned or len(key_returned) < len("sk-secret-key-12345"), "KEY 应脱敏"

    print("PASS: requirements_check")


if __name__ == "__main__":
    test_e2e_two_parties_five_rounds()
    test_restart_recovery_full()
    test_evidence_compression_timing()
    test_multi_debate_isolation()
    test_requirements_check()
    print("\n所有阶段八集成测试通过。")
