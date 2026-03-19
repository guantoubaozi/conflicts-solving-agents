"""
阶段五单元测试：论据压缩 Worker
"""

import asyncio
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import services.storage as storage
import config as cfg


def _setup(tmp: str):
    storage._BASE = Path(tmp) / "debates"
    cfg._CONFIG_PATH = Path(tmp) / "config.json"
    cfg.write_config("https://api.test.com", "sk-test")


def _write_stance_with_evidence(debate_id: str, party_id: str, content: str, status: str = "NONE") -> str:
    evidence_id = str(uuid.uuid4())
    stance = {
        "stance_id": str(uuid.uuid4()),
        "party_id": party_id,
        "debate_id": debate_id,
        "viewpoint": "观点",
        "facts": "",
        "evidence_pool": [{
            "evidence_id": evidence_id,
            "content": content,
            "is_valid": True,
            "created_round": 1,
            "compress_status": status,
        }],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.write_stance(debate_id, party_id, stance)
    return evidence_id


def test_no_trigger_under_threshold():
    """字数 ≤ 5000 时不触发压缩。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id = "d1"
        party_id = "pa"
        content = "论据" * 100  # 200 字，远低于 5000
        _write_stance_with_evidence(debate_id, party_id, content)

        from services.evidence_compressor import check_and_mark_pending
        marked = check_and_mark_pending(debate_id, party_id)
        assert marked == [], f"不应触发压缩，但标记了 {marked}"

        data = storage.read_stance(debate_id, party_id)
        assert data["evidence_pool"][0]["compress_status"] == "NONE"
    print("PASS: no_trigger_under_threshold")


def test_trigger_over_threshold():
    """字数 > 5000 时触发压缩，状态置为 PENDING。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id = "d1"
        party_id = "pa"
        content = "论" * 5001
        eid = _write_stance_with_evidence(debate_id, party_id, content)

        from services.evidence_compressor import check_and_mark_pending
        marked = check_and_mark_pending(debate_id, party_id)
        assert eid in marked

        data = storage.read_stance(debate_id, party_id)
        assert data["evidence_pool"][0]["compress_status"] == "PENDING"
    print("PASS: trigger_over_threshold")


def test_no_duplicate_trigger():
    """已处于 COMPRESSING 或 DONE 时跳过，不重复触发。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id = "d1"
        party_id = "pa"
        content = "论" * 5001

        for status in ("COMPRESSING", "DONE"):
            _write_stance_with_evidence(debate_id, party_id, content, status=status)
            from services.evidence_compressor import check_and_mark_pending
            marked = check_and_mark_pending(debate_id, party_id)
            assert marked == [], f"status={status} 时不应重复触发，但标记了 {marked}"
    print("PASS: no_duplicate_trigger")


def test_compress_state_transition():
    """PENDING → COMPRESSING → DONE 状态流转正确，内容写回文件。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id = "d1"
        party_id = "pa"
        content = "论" * 5001
        eid = _write_stance_with_evidence(debate_id, party_id, content, status="PENDING")

        compressed_text = "压缩后的论据内容，字数在 5000 以内。"

        from services import evidence_compressor
        with patch.object(evidence_compressor, "_call_compress_llm", new=AsyncMock(return_value=compressed_text)):
            asyncio.run(evidence_compressor.compress_evidence_async(debate_id, party_id, eid))

        data = storage.read_stance(debate_id, party_id)
        e = data["evidence_pool"][0]
        assert e["compress_status"] == "DONE", f"期望 DONE，实际 {e['compress_status']}"
        assert e["content"] == compressed_text
        assert len(e["content"]) <= 5000
    print("PASS: compress_state_transition")


def test_compress_result_under_5000():
    """压缩后论据字数 ≤ 5000。"""
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        debate_id = "d1"
        party_id = "pa"
        content = "论" * 6000
        eid = _write_stance_with_evidence(debate_id, party_id, content, status="PENDING")

        # 模拟压缩结果为 4999 字
        compressed_text = "压" * 4999

        from services import evidence_compressor
        with patch.object(evidence_compressor, "_call_compress_llm", new=AsyncMock(return_value=compressed_text)):
            asyncio.run(evidence_compressor.compress_evidence_async(debate_id, party_id, eid))

        data = storage.read_stance(debate_id, party_id)
        assert len(data["evidence_pool"][0]["content"]) <= 5000
    print("PASS: compress_result_under_5000")


if __name__ == "__main__":
    test_no_trigger_under_threshold()
    test_trigger_over_threshold()
    test_no_duplicate_trigger()
    test_compress_state_transition()
    test_compress_result_under_5000()
    print("\n所有阶段五测试通过。")
