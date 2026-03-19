"""
services/fact_organizer.py — 事实库 LLM 整理

追加事实后，LLM 异步整理：
1. 合并语义重复条目
2. 保持真/假标记不变
3. 若"假"事实被新内容修正，改为"真"
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config as cfg
from services import debate_store

_ORGANIZE_PROMPT = """你是事实库整理助手。给定一方的事实文本（可能包含多条，用换行分隔），请：
1. 合并语义重复的条目（保留更完整的表述）
2. 保持每条事实的真/假标记不变（格式：[真] 内容 或 [假] 内容）
3. 若某条"[假]"事实的内容被新增内容修正或补充（语义高度相关），将该条改为"[真]"
4. 返回整理后的事实文本（保持换行分隔格式）
5. 不要添加任何额外说明，只返回整理后的事实文本

注意：如果事实文本中没有 [真]/[假] 标记，则视为全部为真，无需添加标记。"""


async def organize_facts(debate_id: str, party_id: str) -> str:
    """调用 LLM 整理事实库，返回整理后的文本。"""
    stance = debate_store.get_stance(debate_id, party_id)
    if not stance or not stance.facts.strip():
        return stance.facts if stance else ""

    # 获取背景信息（如有）
    prop = debate_store.get_proposition(debate_id)
    background_ctx = ""
    if prop and prop.background:
        background_ctx = f"\n\n【辩论背景前提】{prop.background}"

    conf = cfg.read_config()

    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = ChatOpenAI(
        model=conf.get("model_name", "gpt-4o"),
        base_url=conf["api_url"] or None,
        api_key=conf["api_key"] or "placeholder",
    )

    messages = [
        SystemMessage(content=_ORGANIZE_PROMPT + background_ctx),
        HumanMessage(content=f"请整理以下事实文本：\n\n{stance.facts}"),
    ]

    response = await llm.ainvoke(messages)
    return response.content.strip()
