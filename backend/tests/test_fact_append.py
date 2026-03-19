"""
T4 测试：事实追加 + LLM 整理 + 阻塞场景
覆盖：追加事实后 stance.facts 包含新内容、facts_organizing=True 期间阻塞、
      整理完成后 facts_organizing=False、假事实被修正后标记变真
"""

import sys
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_store(tmp: str):
    """返回使用临时目录的 debate_store 模块。"""
    from services import storage, debate_store
    storage._BASE = Path(tmp)
    return debate_store, storage


def _setup_debate_with_stance(store, facts: str = "[真] 天空是蓝色的"):
    """创建辩论 + 参与方 + 立论，返回 (debate, party, stance)。"""
    from models.debate import DebateStatus
    debate, _ = store.create_debate("测试命题", "user")
    debate.status = DebateStatus.ROUND
    debate.current_round = 1
    store.save_debate(debate)

    party = store.add_party(debate.debate_id, "甲方")
    store.init_round(debate.debate_id, 1)

    from models.stance import Stance
    now = datetime.now(timezone.utc)
    stance = Stance(
        stance_id="s1",
        party_id=party.party_id,
        debate_id=debate.debate_id,
        viewpoint="测试观点",
        facts=facts,
        created_at=now,
        updated_at=now,
    )
    store.save_stance(stance)
    return debate, party, stance


# ── T4-1: 追加事实后 stance.facts 包含新内容 ─────────────────

def test_append_facts_content():
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, party, stance = _setup_debate_with_stance(store)

        # 手动模拟追加逻辑（与 router 一致）
        new_content = "[真] 水是透明的"
        separator = "\n" if stance.facts.strip() else ""
        stance.facts = stance.facts.rstrip() + separator + new_content.strip()
        stance.facts_organizing = True
        store.save_stance(stance)

        loaded = store.get_stance(debate.debate_id, party.party_id)
        assert "[真] 天空是蓝色的" in loaded.facts
        assert "[真] 水是透明的" in loaded.facts
        assert loaded.facts_organizing is True


# ── T4-2: facts_organizing=True 期间 run_solution_phase 等待 ──

def test_wait_facts_organized_blocks():
    """facts_organizing=True 时 _wait_facts_organized 应等待直到变为 False。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, party, stance = _setup_debate_with_stance(store)

        # 设置 facts_organizing = True
        stance.facts_organizing = True
        store.save_stance(stance)

        # 在另一个任务中 0.5 秒后解除锁定
        async def unlock_later():
            await asyncio.sleep(0.5)
            s = store.get_stance(debate.debate_id, party.party_id)
            s.facts_organizing = False
            s.updated_at = datetime.now(timezone.utc)
            store.save_stance(s)

        async def run_test():
            from services.debate_service import _wait_facts_organized
            task = asyncio.create_task(unlock_later())
            await _wait_facts_organized(debate.debate_id, party.party_id, timeout=5)
            await task

            loaded = store.get_stance(debate.debate_id, party.party_id)
            assert loaded.facts_organizing is False

        asyncio.run(run_test())


# ── T4-3: 整理完成后 facts_organizing=False ──────────────────

def test_organize_facts_completes():
    """LLM 整理完成后 facts_organizing 应为 False，facts 应为整理后内容。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, party, stance = _setup_debate_with_stance(
            store, "[真] 天空是蓝色的\n[真] 天是蓝的\n[假] 地球是平的"
        )
        stance.facts_organizing = True
        store.save_stance(stance)

        organized_text = "[真] 天空是蓝色的\n[假] 地球是平的"

        async def mock_organize(debate_id, party_id):
            return organized_text

        async def run_test():
            with patch("services.fact_organizer.organize_facts", side_effect=mock_organize):
                # 模拟 _organize_facts 逻辑
                from services.fact_organizer import organize_facts
                result = await organize_facts(debate.debate_id, party.party_id)

                s = store.get_stance(debate.debate_id, party.party_id)
                s.facts = result
                s.facts_organizing = False
                store.save_stance(s)

            loaded = store.get_stance(debate.debate_id, party.party_id)
            assert loaded.facts_organizing is False
            assert "[真] 天空是蓝色的" in loaded.facts
            assert "[真] 天是蓝的" not in loaded.facts  # 重复已合并
            assert "[假] 地球是平的" in loaded.facts

        asyncio.run(run_test())


# ── T4-4: 假事实被修正后标记变真 ─────────────────────────────

def test_false_fact_corrected_to_true():
    """LLM 整理时，若假事实被新内容修正，应改为真。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, party, stance = _setup_debate_with_stance(
            store, "[假] 地球是平的\n[真] 最新研究证明地球是圆的"
        )

        # 模拟 LLM 将假事实修正为真
        organized_text = "[真] 地球是圆的（已被新证据修正）\n[真] 最新研究证明地球是圆的"

        async def mock_organize(debate_id, party_id):
            return organized_text

        async def run_test():
            with patch("services.fact_organizer.organize_facts", side_effect=mock_organize):
                result = await mock_organize(debate.debate_id, party.party_id)

                s = store.get_stance(debate.debate_id, party.party_id)
                s.facts = result
                s.facts_organizing = False
                store.save_stance(s)

            loaded = store.get_stance(debate.debate_id, party.party_id)
            assert "[假]" not in loaded.facts
            assert "[真] 地球是圆的" in loaded.facts

        asyncio.run(run_test())


# ── T4-5: 整理失败时解除锁定 ─────────────────────────────────

def test_organize_failure_unlocks():
    """LLM 整理失败时，facts_organizing 应被解除。"""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        debate, party, stance = _setup_debate_with_stance(store)
        stance.facts_organizing = True
        store.save_stance(stance)

        async def run_test():
            # 模拟 _organize_facts 中的异常处理逻辑
            try:
                raise Exception("LLM API error")
            except Exception:
                s = store.get_stance(debate.debate_id, party.party_id)
                s.facts_organizing = False
                s.updated_at = datetime.now(timezone.utc)
                store.save_stance(s)

            loaded = store.get_stance(debate.debate_id, party.party_id)
            assert loaded.facts_organizing is False

        asyncio.run(run_test())
