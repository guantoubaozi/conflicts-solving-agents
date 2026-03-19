"""
阶段四单元测试：Agent 实现
测试 Agent 实例化、工具绑定、compress_status 等待逻辑。
不调用真实 LLM。
"""

import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import services.storage as storage
import config as cfg


def _setup(tmp: str):
    storage._BASE = Path(tmp) / "debates"
    cfg._CONFIG_PATH = Path(tmp) / "config.json"
    cfg.write_config("https://api.test.com", "sk-test")


def _create_debate_with_parties(tmp: str) -> tuple[str, str, str]:
    """创建辩论场次和两个辩论方，返回 (debate_id, party_a, party_b)。"""
    from services import debate_store
    debate, _ = debate_store.create_debate("测试命题", "user1")
    debate_id = debate.debate_id
    pa = debate_store.add_party(debate_id, "甲方")
    pb = debate_store.add_party(debate_id, "乙方")
    return debate_id, pa.party_id, pb.party_id


def test_party_agent_instance_isolation():
    """两个不同 party_id 的 Agent 实例互相隔离。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_a, party_b = _create_debate_with_parties(tmp)

        from agents.party_agent import PartyAgent
        agent_a = PartyAgent(debate_id, party_a)
        agent_b = PartyAgent(debate_id, party_b)

        assert agent_a.debate_id == agent_b.debate_id
        assert agent_a.party_id != agent_b.party_id
        assert agent_a.party_id == party_a
        assert agent_b.party_id == party_b
    print("PASS: party_agent_instance_isolation")


def test_party_agent_tool_binding():
    """Agent 工具能正确读取己方论据详情，工具只绑定己方 party_id。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_a, party_b = _create_debate_with_parties(tmp)

        # 写入甲方立论
        from models.stance import Stance, EvidenceItem
        evidence_id = str(uuid.uuid4())
        stance = Stance(
            stance_id=str(uuid.uuid4()),
            party_id=party_a,
            debate_id=debate_id,
            viewpoint="甲方观点",
            facts="甲方事实",
            evidence_pool=[
                EvidenceItem(
                    evidence_id=evidence_id,
                    content="甲方论据内容",
                    created_round=1,
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        storage.write_stance(debate_id, party_a, stance.model_dump(mode="json"))

        # 甲方 Agent 的 read_evidence_detail 工具应返回甲方论据
        from agents.party_agent import _make_party_tools
        tools_a = _make_party_tools(debate_id, party_a)
        read_evidence_tool = next(t for t in tools_a if t.name == "read_evidence_detail")
        result = read_evidence_tool.invoke({"evidence_id": evidence_id})
        assert "甲方论据内容" in result

        # 乙方 Agent 的 read_evidence_detail 工具应返回"不存在"
        tools_b = _make_party_tools(debate_id, party_b)
        read_evidence_tool_b = next(t for t in tools_b if t.name == "read_evidence_detail")
        result_b = read_evidence_tool_b.invoke({"evidence_id": evidence_id})
        assert "不存在" in result_b
    print("PASS: party_agent_tool_binding")


def test_wait_evidence_ready_blocks_on_compressing():
    """存在 COMPRESSING 状态论据时，_wait_evidence_ready 应阻塞直到状态变为 DONE。"""
    import threading
    import time

    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_a, _ = _create_debate_with_parties(tmp)

        # 写入含 COMPRESSING 论据的立论
        from models.stance import Stance, EvidenceItem, CompressStatus
        evidence_id = str(uuid.uuid4())
        stance = Stance(
            stance_id=str(uuid.uuid4()),
            party_id=party_a,
            debate_id=debate_id,
            viewpoint="观点",
            evidence_pool=[
                EvidenceItem(
                    evidence_id=evidence_id,
                    content="论据内容",
                    created_round=1,
                    compress_status=CompressStatus.COMPRESSING,
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        storage.write_stance(debate_id, party_a, stance.model_dump(mode="json"))

        from agents.party_agent import PartyAgent
        agent = PartyAgent(debate_id, party_a)

        # 在后台线程中 0.3s 后将状态改为 DONE
        def finish_compress():
            time.sleep(0.3)
            data = storage.read_stance(debate_id, party_a)
            for e in data["evidence_pool"]:
                if e["evidence_id"] == evidence_id:
                    e["compress_status"] = "DONE"
            storage.write_stance(debate_id, party_a, data)

        t = threading.Thread(target=finish_compress)
        t.start()

        start = time.time()
        agent._wait_evidence_ready(1)
        elapsed = time.time() - start
        t.join()

        assert elapsed >= 0.2, f"应等待至少 0.2s，实际 {elapsed:.2f}s"
    print("PASS: wait_evidence_ready_blocks_on_compressing")


def test_reflection_writes_changelog():
    """write_reflection 工具应将变更记录写入 changelogs.json。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_a, _ = _create_debate_with_parties(tmp)

        from agents.party_agent import _make_party_tools
        tools = _make_party_tools(debate_id, party_a)
        write_reflection_tool = next(t for t in tools if t.name == "write_reflection")

        changes = [{
            "type": "MODIFY_EVIDENCE",
            "target_id": "e1",
            "reason": "对方挑战了该论据",
            "before": "旧内容",
            "after": "新内容",
        }]
        write_reflection_tool.invoke({
            "round_num": 1,
            "content": "反思内容",
            "changes": changes,
        })

        logs = storage.read_changelogs(debate_id, party_a)
        assert len(logs) == 1
        assert logs[0]["change_type"] == "MODIFY_EVIDENCE"
        assert logs[0]["reason"] == "对方挑战了该论据"
    print("PASS: reflection_writes_changelog")


def test_judge_agent_instance():
    """裁判 Agent 实例化正确。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, _, _ = _create_debate_with_parties(tmp)

        from agents.judge_agent import JudgeAgent
        judge = JudgeAgent(debate_id)
        assert judge.debate_id == debate_id
    print("PASS: judge_agent_instance")


def test_judge_tools_read_stance_detail():
    """裁判工具 read_stance_detail 能读取指定方立论。"""
    import json
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id, party_a, party_b = _create_debate_with_parties(tmp)

        from models.stance import Stance
        for pid, vp in [(party_a, "甲方观点"), (party_b, "乙方观点")]:
            s = Stance(
                stance_id=str(uuid.uuid4()),
                party_id=pid,
                debate_id=debate_id,
                viewpoint=vp,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            storage.write_stance(debate_id, pid, s.model_dump(mode="json"))

        from agents.judge_agent import _make_judge_tools
        tools = _make_judge_tools(debate_id)
        read_stance = next(t for t in tools if t.name == "read_stance_detail")
        result_a = json.loads(read_stance.invoke({"party_id": party_a}))
        assert result_a["viewpoint"] == "甲方观点"
        result_b = json.loads(read_stance.invoke({"party_id": party_b}))
        assert result_b["viewpoint"] == "乙方观点"
    print("PASS: judge_tools_read_stance_detail")


if __name__ == "__main__":
    test_party_agent_instance_isolation()
    test_party_agent_tool_binding()
    test_wait_evidence_ready_blocks_on_compressing()
    test_reflection_writes_changelog()
    test_judge_agent_instance()
    test_judge_tools_read_stance_detail()
    print("\n所有阶段四测试通过。")
