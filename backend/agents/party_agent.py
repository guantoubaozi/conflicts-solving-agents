"""
agents/party_agent.py — 辩论方 Agent

无状态调用模式：每次调用手动组装精简上下文，避免历史消息累积导致上下文膨胀。
每个辩论方独立实例，不再依赖 checkpointer 累积对话历史。
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import config as cfg
from services import storage, debate_store
from models.stance import CompressStatus


# ── 系统提示词（精简版，聚焦具体可落地） ──────────────────

_DEBATE_RULES = """你是辩论方 Agent，参与一场以"解决问题"为目标的结构化辩论。

**核心原则：辩论是手段，不是目的。你的目标不是驳倒对方赢得辩论，而是与各方协作，收敛到一个具体、可落地、可实施的最佳解决方案。**

你的职责：

1. **生成解决方案**：
   - 优先支持己方观点，同时积极寻求与其他方的折中方案
   - 方案不得与己方标记为"真"的事实相矛盾
   - 方案不得违背已锁定的共识
   - **必须优先回应裁判指定的 focus_next（下一轮聚焦矛盾）**
   - **方案必须具体、可落地、可执行，包含明确的实施步骤和预期效果**
   - **禁止引入新的议题维度，聚焦收敛现有矛盾**
   - 引用论据前必须先将其纳入论据库

2. **质疑（非对抗性）**：
   - 目标不是"证明对方为假"，而是"指出对方方案的实施障碍和现实困难"
   - 质疑须具体、建设性，指出问题的同时建议可能的解决方向
   - 不得质疑已锁定的共识

3. **反思与折中**：
   - 认真考虑对方指出的实施障碍
   - 若己方方案确有实施困难，主动提出折中修改方案
   - 若可通过补充限定条件解决障碍，优先修改而非坚持原方案
   - 若确实无法成立，果断放弃并标记为"假"

4. **字数限制**：每轮辩论使用的论据总字数 ≤ 5000 字。

5. **论据引用规则**：引用论据前必须检查 compress_status，COMPRESSING 状态时等待完成后再继续。

6. **收敛纪律**：
   - 每轮方案的讨论范围必须 ≤ 上一轮，不得扩展
   - 已锁定的共识视为既定前提，直接在此基础上推进
   - 回应须紧扣裁判指定的聚焦矛盾，不得偏离
"""


def _get_llm() -> ChatOpenAI:
    conf = cfg.read_config()
    return ChatOpenAI(
        model=conf.get("model_name", "gpt-4o"),
        base_url=conf["api_url"] or None,
        api_key=conf["api_key"] or "placeholder",
        streaming=True,
    )


# ── 上下文构建辅助函数 ────────────────────────────────────

def _build_soul_context(debate_id: str, party_id: str) -> str:
    """构建辩论方性格上下文（若已设置）。"""
    party = debate_store.get_party(debate_id, party_id)
    if not party or not party.soul:
        return ""
    return f"【你的性格与思考风格】\n{party.soul}"

def _build_proposition_context(debate_id: str) -> str:
    """构建命题上下文（固定，每轮都需要）。"""
    data = storage.read_proposition(debate_id)
    if not data:
        return ""
    content = data.get("content", "")
    background = data.get("background", "")
    ctx = f"【辩论命题】\n{content}"
    if background:
        ctx += f"\n\n【背景前提（所有方承认为真，不得违背）】\n{background}"
    return ctx


def _build_stance_summary(debate_id: str, party_id: str) -> str:
    """构建己方立论摘要：仅包含观点 + 有效事实 + 有效论据的标题/ID。"""
    data = storage.read_stance(debate_id, party_id)
    if not data:
        return "（立论尚未提交）"

    parts = []
    # 观点
    viewpoint = data.get("viewpoint", "")
    if viewpoint:
        parts.append(f"【己方观点】\n{viewpoint}")

    # 有效事实（仅保留标记为真的）
    facts = data.get("facts", "")
    if facts:
        # 过滤出 [真] 的事实，或无标记的（默认为真）
        lines = facts.strip().split("\n")
        valid_facts = [l for l in lines if l.strip() and not l.strip().startswith("[假]")]
        if valid_facts:
            parts.append(f"【己方有效事实（{len(valid_facts)}条）】\n" + "\n".join(valid_facts))

    # 有效论据摘要（仅 ID + 前100字预览，不含全文）
    evidence_pool = data.get("evidence_pool", [])
    valid_evidence = [e for e in evidence_pool if e.get("is_valid", True)]
    if valid_evidence:
        evidence_lines = []
        for e in valid_evidence:
            eid = e["evidence_id"]
            preview = e.get("content", "")[:100]
            status = e.get("compress_status", "NONE")
            evidence_lines.append(f"  - {eid}: {preview}...（压缩状态: {status}）")
        parts.append(f"【己方有效论据（{len(valid_evidence)}条，仅预览）】\n" + "\n".join(evidence_lines))

    return "\n\n".join(parts)


def _build_changelog_summary(debate_id: str, party_id: str, round_num: int) -> str:
    """构建上一轮变更摘要。"""
    if round_num <= 1:
        return ""
    logs = debate_store.get_changelogs(debate_id, party_id)
    prev_logs = [l for l in logs if l.round == round_num - 1]
    if not prev_logs:
        return ""

    lines = [f"【上一轮（第{round_num - 1}轮）己方变更记录（{len(prev_logs)}条）】"]
    for log in prev_logs:
        lines.append(f"  - [{log.change_type.value}] {log.target_id}: {log.reason}")
    return "\n".join(lines)


def _build_judge_contradictions(debate_id: str, round_num: int) -> str:
    """构建裁判指出的矛盾 + 聚焦指令 + 锁定共识。"""
    summary = debate_store.get_judge_summary(debate_id, round_num)
    if not summary:
        return ""

    parts = []
    # 锁定共识（最高优先级，作为不可违背的前提）
    if summary.locked_consensus:
        parts.append(f"【已锁定共识（不可推翻，须作为既定前提）】\n{summary.locked_consensus}")

    # 聚焦指令（下一轮必须优先解决的矛盾）
    if summary.focus_next:
        parts.append(f"【⚠️ 下一轮聚焦指令（必须优先回应）】\n{summary.focus_next}")

    if summary.contradictions:
        parts.append(f"【第{round_num}轮裁判指出的矛盾】\n{summary.contradictions}")
    if summary.consensus:
        parts.append(f"【第{round_num}轮新增共识】\n{summary.consensus}")
    return "\n\n".join(parts)


def _build_judge_full_summary(debate_id: str, round_num: int) -> str:
    """构建裁判完整梳理结果（用于质疑阶段）。"""
    summary = debate_store.get_judge_summary(debate_id, round_num)
    if not summary:
        return f"（第{round_num}轮裁判梳理尚未完成）"

    parts = [f"【第{round_num}轮裁判梳理结果】"]
    if summary.locked_consensus:
        parts.append(f"已锁定共识（不可质疑）：\n{summary.locked_consensus}")
    if summary.focus_next:
        parts.append(f"⚠️ 聚焦指令：\n{summary.focus_next}")
    if summary.consensus:
        parts.append(f"本轮新增共识：\n{summary.consensus}")
    if summary.contradictions:
        parts.append(f"矛盾：\n{summary.contradictions}")
    if summary.combined_solution:
        parts.append(f"综合方案：\n{summary.combined_solution}")
    return "\n\n".join(parts)


def _build_challenges_context(debate_id: str, round_num: int, challenger_party_ids: list[str]) -> str:
    """构建对方挑战内容（用于反思阶段）。"""
    parts = []
    for cid in challenger_party_ids:
        data = storage.read_challenge(debate_id, round_num, cid)
        if data:
            party = debate_store.get_party(debate_id, cid)
            name = party.name if party else cid
            content = data.get("content", "")
            parts.append(f"【{name}（{cid}）的挑战】\n{content}")
    return "\n\n".join(parts) if parts else "（本轮无挑战内容）"


# ── 工具集（保持不变，agent 仍需通过 tool 写入结果） ──────

def _make_party_tools(debate_id: str, party_id: str):
    """为辩论方 Agent 创建工具集。读取类工具已精简（上下文由 prompt 注入），保留写入类工具。"""

    @tool
    def read_evidence_detail(evidence_id: str) -> str:
        """读取指定论据的完整内容。仅在需要引用某条论据时调用。"""
        stance_data = storage.read_stance(debate_id, party_id)
        if not stance_data:
            return "立论不存在。"
        for e in stance_data.get("evidence_pool", []):
            if e["evidence_id"] == evidence_id:
                return json.dumps(e, ensure_ascii=False, indent=2)
        return f"论据 {evidence_id} 不存在。"

    @tool
    def check_evidence_compress_status(evidence_id: str) -> str:
        """检查指定论据的压缩状态。返回 NONE/PENDING/COMPRESSING/DONE。"""
        stance_data = storage.read_stance(debate_id, party_id)
        if not stance_data:
            return "NONE"
        for e in stance_data.get("evidence_pool", []):
            if e["evidence_id"] == evidence_id:
                return e.get("compress_status", "NONE")
        return "NOT_FOUND"

    @tool
    def write_solution(round_num: int, content: str) -> str:
        """将己方解决方案写入持久化文件。"""
        # 幂等性：如果本轮已有方案则覆盖而非新建
        existing = debate_store.get_solution(debate_id, round_num, party_id)
        if existing:
            existing.content = content
            existing.created_at = datetime.now(timezone.utc)
            debate_store.save_solution(existing)
            return f"解决方案已更新（round={round_num}）。"
        from models.solution import Solution
        sol = Solution(
            solution_id=str(uuid.uuid4()),
            debate_id=debate_id,
            party_id=party_id,
            round=round_num,
            content=content,
            created_at=datetime.now(timezone.utc),
        )
        debate_store.save_solution(sol)
        return f"解决方案已保存（round={round_num}）。"

    @tool
    def write_challenge(round_num: int, content: str) -> str:
        """将己方挑战内容写入持久化文件。"""
        storage.write_challenge(debate_id, round_num, party_id, {
            "party_id": party_id,
            "round": round_num,
            "content": content,
        })
        return f"挑战内容已保存（round={round_num}）。"

    @tool
    def write_reflection(round_num: int, content: str, changes: list) -> str:
        """将己方反思结果写入持久化文件。changes 为变更列表，每项含 type/target_id/reason/before/after。"""
        from models.changelog import ChangeLog, ChangeType

        storage.write_reflection(debate_id, round_num, party_id, {
            "party_id": party_id,
            "round": round_num,
            "content": content,
            "changes": changes,
        })

        for ch in changes:
            try:
                log = ChangeLog(
                    log_id=str(uuid.uuid4()),
                    debate_id=debate_id,
                    party_id=party_id,
                    round=round_num,
                    change_type=ChangeType(ch["type"]),
                    target_id=ch["target_id"],
                    reason=ch["reason"],
                    before_content=ch.get("before", ""),
                    after_content=ch.get("after", ""),
                    created_at=datetime.now(timezone.utc),
                )
                debate_store.append_changelog(log)
            except Exception:
                pass

        return f"反思结果已保存（round={round_num}），变更记录 {len(changes)} 条。"

    @tool
    def update_evidence(evidence_id: str, new_content: str, is_valid: bool = True) -> str:
        """更新己方论据库中某条论据的内容或有效性标记。"""
        stance_data = storage.read_stance(debate_id, party_id)
        if not stance_data:
            return "立论不存在。"
        for e in stance_data.get("evidence_pool", []):
            if e["evidence_id"] == evidence_id:
                e["content"] = new_content
                e["is_valid"] = is_valid
                if is_valid and len(new_content) > 5000 and e.get("compress_status") not in ("COMPRESSING", "DONE"):
                    e["compress_status"] = "PENDING"
                storage.write_stance(debate_id, party_id, stance_data)
                return f"论据 {evidence_id} 已更新。"
        return f"论据 {evidence_id} 不存在。"

    return [
        read_evidence_detail,
        check_evidence_compress_status,
        write_solution,
        write_challenge,
        write_reflection,
        update_evidence,
    ]


# ── PartyAgent 主类 ───────────────────────────────────────

class PartyAgent:
    """
    辩论方 Agent 封装。

    无状态模式：每次调用创建新的 agent（不使用 checkpointer），
    通过 SystemMessage 注入精简上下文，避免历史消息累积。
    """

    def __init__(self, debate_id: str, party_id: str):
        self.debate_id = debate_id
        self.party_id = party_id

    def _create_agent(self, system_context: str):
        """创建无状态 agent，将精简上下文作为 system prompt 的一部分。"""
        tools = _make_party_tools(self.debate_id, self.party_id)
        llm = _get_llm()
        full_prompt = _DEBATE_RULES + "\n\n---\n\n" + system_context
        return create_react_agent(
            model=llm,
            tools=tools,
            prompt=full_prompt,
        )

    def _wait_evidence_ready(self, round_num: int) -> None:
        """阻塞等待所有待引用论据压缩完成。"""
        while True:
            stance_data = storage.read_stance(self.debate_id, self.party_id)
            if not stance_data:
                break
            compressing = [
                e for e in stance_data.get("evidence_pool", [])
                if e.get("is_valid", True) and e.get("compress_status") == "COMPRESSING"
            ]
            if not compressing:
                break
            import time
            time.sleep(1)

    def generate_solution(self, round_num: int) -> str:
        """
        生成本轮解决方案。

        注入上下文：
        - 命题（固定）
        - 己方立论摘要（观点 + 有效事实 + 论据预览）
        - 上一轮裁判指出的矛盾 + 共识
        - 上一轮己方变更记录
        """
        self._wait_evidence_ready(round_num)

        context_parts = [
            _build_soul_context(self.debate_id, self.party_id),
            _build_proposition_context(self.debate_id),
            _build_stance_summary(self.debate_id, self.party_id),
        ]

        # 第 2 轮起，注入上一轮裁判矛盾和变更记录
        if round_num > 1:
            context_parts.append(
                _build_judge_contradictions(self.debate_id, round_num - 1)
            )
            context_parts.append(
                _build_changelog_summary(self.debate_id, self.party_id, round_num)
            )

        system_context = "\n\n".join(p for p in context_parts if p)

        agent = self._create_agent(system_context)
        prompt = (
            f"现在是第 {round_num} 轮辩论。请基于上述上下文生成本轮解决方案。\n\n"
            f"要求：\n"
            f"- 若上下文中有【聚焦指令】，必须优先针对该矛盾提出具体折中方案\n"
            f"- 方案必须具体、可落地、可执行，包含明确的实施步骤\n"
            f"- 不得引入新的议题维度，聚焦收敛现有矛盾\n"
            f"- 已锁定的共识视为既定前提，在此基础上推进\n"
            f"- 如需引用论据，先用 read_evidence_detail 获取全文\n"
            f"- 最后调用 write_solution(round_num={round_num}, content=...) 保存方案"
        )
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        return result["messages"][-1].content

    def generate_challenge(self, round_num: int) -> str:
        """
        生成本轮挑战内容。

        注入上下文：
        - 命题（固定）
        - 己方立论摘要
        - 本轮裁判完整梳理结果（含矛盾详情）
        """
        self._wait_evidence_ready(round_num)

        context_parts = [
            _build_soul_context(self.debate_id, self.party_id),
            _build_proposition_context(self.debate_id),
            _build_stance_summary(self.debate_id, self.party_id),
            _build_judge_full_summary(self.debate_id, round_num),
        ]

        system_context = "\n\n".join(p for p in context_parts if p)

        agent = self._create_agent(system_context)
        prompt = (
            f"现在是第 {round_num} 轮辩论的质疑阶段。\n\n"
            f"请基于裁判梳理结果中的矛盾，对其他方的方案提出建设性质疑：\n"
            f"- 目标不是驳倒对方，而是指出对方方案的实施障碍和现实困难\n"
            f"- 质疑须具体，指出问题的同时建议可能的解决方向或折中思路\n"
            f"- 不得质疑已锁定的共识\n"
            f"- 聚焦裁判指定的聚焦矛盾，不要发散到其他议题\n"
            f"最后调用 write_challenge(round_num={round_num}, content=...) 保存。"
        )
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        return result["messages"][-1].content

    def generate_reflection(self, round_num: int, challenger_party_ids: list[str]) -> str:
        """
        生成本轮反思内容。

        注入上下文：
        - 命题（固定）
        - 己方立论摘要
        - 对方挑战内容
        """
        context_parts = [
            _build_soul_context(self.debate_id, self.party_id),
            _build_proposition_context(self.debate_id),
            _build_stance_summary(self.debate_id, self.party_id),
            _build_challenges_context(self.debate_id, round_num, challenger_party_ids),
        ]

        system_context = "\n\n".join(p for p in context_parts if p)

        agent = self._create_agent(system_context)
        challengers = "、".join(challenger_party_ids)
        prompt = (
            f"现在是第 {round_num} 轮辩论的反思阶段。\n\n"
            f"请针对上述各方指出的实施障碍，认真反思并回应：\n"
            f"- 若己方方案确有实施困难，主动提出折中修改方案\n"
            f"- 若可通过补充限定条件解决障碍，调用 update_evidence 修改\n"
            f"- 若确实无法成立，果断放弃并调用 update_evidence 标记 is_valid=False\n"
            f"- 目标是推动收敛，而非坚持己见\n"
            f"最后调用 write_reflection(round_num={round_num}, content=..., changes=[...]) 保存结果。"
        )
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        return result["messages"][-1].content
