"""
services/evidence_compressor.py — 论据自动压缩 Worker

触发条件：单条论据字数 > 5000 时自动触发。
状态机：NONE → PENDING → COMPRESSING → DONE
防重复：已处于 COMPRESSING 或 DONE 时跳过。
"""

import asyncio
import uuid
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import storage
from models.stance import CompressStatus

_COMPRESS_THRESHOLD = 5000


def check_and_mark_pending(debate_id: str, party_id: str) -> list[str]:
    """
    检查论据库，将超过阈值且状态为 NONE 的论据标记为 PENDING。
    返回被标记的 evidence_id 列表。
    """
    stance_data = storage.read_stance(debate_id, party_id)
    if not stance_data:
        return []

    marked = []
    changed = False
    for e in stance_data.get("evidence_pool", []):
        if not e.get("is_valid", True):
            continue
        status = e.get("compress_status", "NONE")
        if status in ("COMPRESSING", "DONE"):
            continue
        if len(e.get("content", "")) > _COMPRESS_THRESHOLD:
            e["compress_status"] = "PENDING"
            marked.append(e["evidence_id"])
            changed = True

    if changed:
        storage.write_stance(debate_id, party_id, stance_data)
    return marked


async def compress_evidence_async(debate_id: str, party_id: str, evidence_id: str) -> None:
    """
    异步压缩单条论据：PENDING → COMPRESSING → DONE。
    调用 AI 模型将论据压缩至 5000 字以内。
    """
    # 标记为 COMPRESSING
    stance_data = storage.read_stance(debate_id, party_id)
    if not stance_data:
        return

    target = None
    for e in stance_data.get("evidence_pool", []):
        if e["evidence_id"] == evidence_id:
            target = e
            break
    if not target:
        return

    # 防重复：已在 COMPRESSING 或 DONE 时跳过
    if target.get("compress_status") in ("COMPRESSING", "DONE"):
        return

    target["compress_status"] = "COMPRESSING"
    storage.write_stance(debate_id, party_id, stance_data)

    try:
        compressed = await _call_compress_llm(target["content"])
    except Exception:
        # 压缩失败时回退到 PENDING，允许重试
        stance_data = storage.read_stance(debate_id, party_id)
        for e in stance_data.get("evidence_pool", []):
            if e["evidence_id"] == evidence_id:
                e["compress_status"] = "PENDING"
                break
        storage.write_stance(debate_id, party_id, stance_data)
        return

    # 写回压缩结果，标记为 DONE
    stance_data = storage.read_stance(debate_id, party_id)
    for e in stance_data.get("evidence_pool", []):
        if e["evidence_id"] == evidence_id:
            e["content"] = compressed
            e["compress_status"] = "DONE"
            break
    storage.write_stance(debate_id, party_id, stance_data)


async def _call_compress_llm(content: str) -> str:
    """调用 AI 模型压缩论据内容至 5000 字以内。"""
    import config as cfg
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    conf = cfg.read_config()
    llm = ChatOpenAI(
        model="gpt-4o",
        base_url=conf["api_url"] or None,
        api_key=conf["api_key"] or "placeholder",
    )

    messages = [
        SystemMessage(content=(
            "你是一个文本压缩助手。请将以下论据内容压缩至 5000 字以内，"
            "保留核心论证内容，去除冗余表述。直接输出压缩后的内容，不要添加任何说明。"
        )),
        HumanMessage(content=content),
    ]
    response = await llm.ainvoke(messages)
    return response.content


async def run_pending_compressions(debate_id: str, party_id: str) -> None:
    """
    扫描论据库，对所有 PENDING 状态的论据启动异步压缩任务。
    """
    stance_data = storage.read_stance(debate_id, party_id)
    if not stance_data:
        return

    tasks = []
    for e in stance_data.get("evidence_pool", []):
        if e.get("compress_status") == "PENDING":
            tasks.append(compress_evidence_async(debate_id, party_id, e["evidence_id"]))

    if tasks:
        await asyncio.gather(*tasks)
