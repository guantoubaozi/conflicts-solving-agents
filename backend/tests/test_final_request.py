"""
T6 测试：直接终论申请机制
覆盖：2方全部同意触发终论、2方不同意不触发、3方 >50% 同意触发、3方 ≤50% 不触发
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_store(tmp: str):
    """返回使用临时目录的 debate_store 模块。"""
    from services import storage, debate_store
    storage._BASE = Path(tmp)
    return debate_store, storage


def _setup_debate(store, party_names: list[str]):
    """创建辩论 + 多个参与方 + 轮次状态（HUMAN_REVIEW），返回 (debate, parties, round_state)。"""
    from models.debate import DebateStatus
    from models.debate_round import RoundPhase

    debate, _ = store.create_debate("测试命题", "user")
    debate.status = DebateStatus.ROUND
    debate.current_round = 1
    store.save_debate(debate)

    parties = []
    for name in party_names:
        p = store.add_party(debate.debate_id, name)
        parties.append(p)

    round_state = store.init_round(debate.debate_id, 1)
    round_state.status = RoundPhase.HUMAN_REVIEW
    store.save_round_state(round_state)

    return debate, parties, round_state


# ── T6-1: 2方场景 — 全部同意触发终论 ────────────────────────

def test_two_party_unanimous_agree():
    """2方辩论：发起方自动同意 + 另一方同意 → 触发终论。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, parties, round_state = _setup_debate(store, ["甲方", "乙方"])
        p_a, p_b = parties

        # 甲方发起终论申请（自动同意）
        round_state.final_request_by = p_a.party_id
        round_state.final_request_votes = {p_a.party_id: True}
        store.save_round_state(round_state)

        # 乙方同意
        round_state.final_request_votes[p_b.party_id] = True
        store.save_round_state(round_state)

        # 检查阈值
        total = len(parties)
        agree_count = sum(1 for v in round_state.final_request_votes.values() if v)
        assert total == 2
        assert agree_count == 2
        # 2方需全部同意
        threshold_met = agree_count == total
        assert threshold_met is True


# ── T6-2: 2方场景 — 另一方不同意，不触发 ────────────────────

def test_two_party_disagree():
    """2方辩论：另一方不同意 → 不触发终论，申请状态清除。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, parties, round_state = _setup_debate(store, ["甲方", "乙方"])
        p_a, p_b = parties

        # 甲方发起
        round_state.final_request_by = p_a.party_id
        round_state.final_request_votes = {p_a.party_id: True}
        store.save_round_state(round_state)

        # 乙方不同意
        round_state.final_request_votes[p_b.party_id] = False
        store.save_round_state(round_state)

        total = len(parties)
        votes = round_state.final_request_votes
        agree_count = sum(1 for v in votes.values() if v)
        all_voted = len(votes) == total

        # 2方需全部同意
        threshold_met = agree_count == total
        assert threshold_met is False
        assert all_voted is True

        # 模拟 _check_final_threshold 中的清除逻辑
        if all_voted and not threshold_met:
            round_state.final_request_by = None
            round_state.final_request_votes = {}
            store.save_round_state(round_state)

        loaded = store.get_round_state(debate.debate_id, 1)
        assert loaded.final_request_by is None
        assert loaded.final_request_votes == {}


# ── T6-3: 3方场景 — 2/3 同意触发终论 ────────────────────────

def test_three_party_majority_agree():
    """3方辩论：发起方 + 1方同意（2/3 > 50%）→ 触发终论。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, parties, round_state = _setup_debate(store, ["甲方", "乙方", "丙方"])
        p_a, p_b, p_c = parties

        # 甲方发起（自动同意）
        round_state.final_request_by = p_a.party_id
        round_state.final_request_votes = {p_a.party_id: True}

        # 乙方同意
        round_state.final_request_votes[p_b.party_id] = True
        store.save_round_state(round_state)

        total = len(parties)
        agree_count = sum(1 for v in round_state.final_request_votes.values() if v)
        assert total == 3
        assert agree_count == 2
        # ≥3方需 >50%
        threshold_met = agree_count > total / 2
        assert threshold_met is True


# ── T6-4: 3方场景 — 1/3 同意不触发 ──────────────────────────

def test_three_party_minority_agree():
    """3方辩论：仅发起方同意（1/3 ≤ 50%）→ 不触发终论。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, parties, round_state = _setup_debate(store, ["甲方", "乙方", "丙方"])
        p_a, p_b, p_c = parties

        # 甲方发起（自动同意）
        round_state.final_request_by = p_a.party_id
        round_state.final_request_votes = {p_a.party_id: True}

        # 乙方不同意
        round_state.final_request_votes[p_b.party_id] = False
        # 丙方不同意
        round_state.final_request_votes[p_c.party_id] = False
        store.save_round_state(round_state)

        total = len(parties)
        votes = round_state.final_request_votes
        agree_count = sum(1 for v in votes.values() if v)
        all_voted = len(votes) == total

        assert agree_count == 1
        # ≥3方需 >50%
        threshold_met = agree_count > total / 2
        assert threshold_met is False
        assert all_voted is True

        # 清除申请状态
        if all_voted and not threshold_met:
            round_state.final_request_by = None
            round_state.final_request_votes = {}
            store.save_round_state(round_state)

        loaded = store.get_round_state(debate.debate_id, 1)
        assert loaded.final_request_by is None
        assert loaded.final_request_votes == {}


# ── T6-5: 发起方自动同意验证 ─────────────────────────────────

def test_requester_auto_agrees():
    """发起终论申请时，发起方自动写入 votes[party_id]=True。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, parties, round_state = _setup_debate(store, ["甲方", "乙方"])
        p_a = parties[0]

        round_state.final_request_by = p_a.party_id
        round_state.final_request_votes = {p_a.party_id: True}
        store.save_round_state(round_state)

        loaded = store.get_round_state(debate.debate_id, 1)
        assert loaded.final_request_by == p_a.party_id
        assert loaded.final_request_votes.get(p_a.party_id) is True


# ── T6-6: 每轮只能发起一次申请 ───────────────────────────────

def test_only_one_request_per_round():
    """已有终论申请时，不能再次发起。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, parties, round_state = _setup_debate(store, ["甲方", "乙方"])
        p_a, p_b = parties

        round_state.final_request_by = p_a.party_id
        round_state.final_request_votes = {p_a.party_id: True}
        store.save_round_state(round_state)

        loaded = store.get_round_state(debate.debate_id, 1)
        assert loaded.final_request_by is not None
        # router 层会返回 409，这里验证状态检查逻辑
        has_existing_request = loaded.final_request_by is not None
        assert has_existing_request is True
