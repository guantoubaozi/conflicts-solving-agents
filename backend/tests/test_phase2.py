"""
阶段二单元测试：数据模型
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

NOW = datetime(2026, 3, 18, 12, 0, 0)


def test_debate_model():
    from models.debate import Debate, DebateStatus

    d = Debate(
        debate_id="d1",
        proposition_id="p1",
        status=DebateStatus.ROUND,
        current_round=2,
        created_at=NOW,
        updated_at=NOW,
    )
    assert d.status == DebateStatus.ROUND
    assert d.current_round == 2

    # 枚举值覆盖
    for v in ["INIT", "STANCE", "ROUND", "FINAL"]:
        DebateStatus(v)
    print("PASS: debate_model")


def test_proposition_model():
    from models.proposition import Proposition

    p = Proposition(
        proposition_id="prop1",
        debate_id="d1",
        content="命题内容",
        created_by="party_a",
        created_at=NOW,
    )
    assert p.content == "命题内容"
    print("PASS: proposition_model")


def test_party_model():
    from models.party import Party, PartyStatus

    p = Party(party_id="pa", debate_id="d1", name="甲方", joined_round=0)
    assert p.status == PartyStatus.ACTIVE
    assert p.joined_round == 0

    for v in ["ACTIVE", "CONFIRMED"]:
        PartyStatus(v)
    print("PASS: party_model")


def test_evidence_item_compress_status():
    from models.stance import EvidenceItem, CompressStatus

    e = EvidenceItem(evidence_id="e1", content="论据内容", created_round=1)
    assert e.compress_status == CompressStatus.NONE
    assert e.is_valid is True

    for v in ["NONE", "PENDING", "COMPRESSING", "DONE"]:
        CompressStatus(v)
    print("PASS: evidence_item_compress_status")


def test_stance_model():
    from models.stance import Stance, EvidenceItem, CompressStatus

    e = EvidenceItem(
        evidence_id="e1",
        content="论据",
        created_round=1,
        compress_status=CompressStatus.DONE,
    )
    s = Stance(
        stance_id="s1",
        party_id="pa",
        debate_id="d1",
        viewpoint="我方观点",
        facts="事实内容",
        evidence_pool=[e],
        created_at=NOW,
        updated_at=NOW,
    )
    assert len(s.evidence_pool) == 1
    assert s.evidence_pool[0].compress_status == CompressStatus.DONE
    print("PASS: stance_model")


def test_solution_model():
    from models.solution import Solution

    sol = Solution(
        solution_id="sol1",
        debate_id="d1",
        party_id="pa",
        round=1,
        content="方案内容",
        created_at=NOW,
    )
    assert sol.is_valid is True
    assert sol.invalid_reason == ""
    print("PASS: solution_model")


def test_judge_summary_model():
    from models.judge_summary import JudgeSummary

    js = JudgeSummary(
        summary_id="js1",
        debate_id="d1",
        round=1,
        consensus="共识内容",
        contradictions="矛盾内容",
        combined_solution="综合方案",
        has_contradiction=True,
        created_at=NOW,
    )
    assert js.has_contradiction is True
    print("PASS: judge_summary_model")


def test_debate_round_model():
    from models.debate_round import DebateRound, RoundPhase

    r = DebateRound(
        round_id="r1",
        debate_id="d1",
        round=1,
        status=RoundPhase.HUMAN_REVIEW,
        human_confirmed=["pa"],
        created_at=NOW,
    )
    assert r.completed_at is None
    assert "pa" in r.human_confirmed

    for v in ["SOLUTION", "JUDGE", "DEBATE", "HUMAN_REVIEW", "DONE"]:
        RoundPhase(v)
    print("PASS: debate_round_model")


def test_changelog_model():
    from models.changelog import ChangeLog, ChangeType

    cl = ChangeLog(
        log_id="cl1",
        debate_id="d1",
        party_id="pa",
        round=2,
        change_type=ChangeType.MODIFY_EVIDENCE,
        target_id="e1",
        reason="对方挑战",
        before_content="旧内容",
        after_content="新内容",
        created_at=NOW,
    )
    assert cl.change_type == ChangeType.MODIFY_EVIDENCE

    for v in ["MODIFY_FACT", "MODIFY_EVIDENCE", "ABANDON_EVIDENCE"]:
        ChangeType(v)
    print("PASS: changelog_model")


def test_serialization_roundtrip():
    """序列化/反序列化：写入 JSON 再读回，字段无丢失。"""
    from models.stance import Stance, EvidenceItem, CompressStatus

    e = EvidenceItem(evidence_id="e1", content="论据", created_round=1, compress_status=CompressStatus.PENDING)
    s = Stance(
        stance_id="s1",
        party_id="pa",
        debate_id="d1",
        viewpoint="观点",
        facts="事实",
        evidence_pool=[e],
        created_at=NOW,
        updated_at=NOW,
    )
    raw = s.model_dump_json()
    s2 = Stance.model_validate_json(raw)
    assert s2.evidence_pool[0].compress_status == CompressStatus.PENDING
    assert s2.viewpoint == "观点"
    print("PASS: serialization_roundtrip")


if __name__ == "__main__":
    test_debate_model()
    test_proposition_model()
    test_party_model()
    test_evidence_item_compress_status()
    test_stance_model()
    test_solution_model()
    test_judge_summary_model()
    test_debate_round_model()
    test_changelog_model()
    test_serialization_roundtrip()
    print("\n所有阶段二测试通过。")
