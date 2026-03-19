"""
agents/judge_agent.py — 裁判 Agent

无状态调用模式：每次调用手动组装精简上下文。
负责有效性检查、合规性检查、共识与矛盾提取、收敛引导、共识锁定、终论裁决。
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import config as cfg
from services import storage, debate_store
from models.judge_summary import JudgeSummary
from models.solution import Solution


_JUDGE_RULES = """你是辩论裁判 Agent。你的核心使命不是评判辩论的精彩程度，而是引导各方高效收敛到一个具体、可落地、可实施的解决方案。

你的职责：

1. **有效性检查**：检查各方方案是否围绕命题展开；不符合命题的方案标记为本轮无效。

2. **合规性检查**：
   - 方案不得与己方标记为"真"的事实相矛盾
   - 方案不得违背已锁定的共识
   - 论据须先入库再使用

3. **共识提取与锁定**：
   - 提取本轮各方均认可的内容作为"新增共识"
   - 将新增共识与历史已锁定共识合并，形成"累积锁定共识"
   - 已锁定的共识在后续轮次中不可被挑战或推翻

4. **矛盾提取与优先级排序**：
   - 提取各方存在分歧的内容
   - 按"对最终可实施方案的影响程度"从高到低排序
   - 明确标注每个矛盾的核心分歧点

5. **收敛引导（focus_next）**：
   - 从排序后的矛盾中选出排名第一的矛盾
   - 在 focus_next 中明确指出：下一轮各方必须优先解决这个矛盾
   - focus_next 须具体说明矛盾的焦点是什么、各方的分歧在哪里
   - 明确要求各方提出针对该矛盾的具体折中方案，而非泛泛讨论

6. **终论裁决**：
   - 无矛盾时：综合各方方案给出唯一最终解决方案
   - 满 5 轮时：选出实现最简单、代价最小的方案
"""


def _get_llm() -> ChatOpenAI:
    conf = cfg.read_config()
    return ChatOpenAI(
        model=conf.get("model_name", "gpt-4o"),
        base_url=conf["api_url"] or None,
        api_key=conf["api_key"] or "placeholder",
        streaming=True,
    )


# ── 上下文构建 ────────────────────────────────────────────

def _build_judge_proposition_context(debate_id: str) -> str:
    """命题上下文。"""
    data = storage.read_proposition(debate_id)
    if not data:
        return ""
    content = data.get("content", "")
    background = data.get("background", "")
    ctx = f"【辩论命题】\n{content}"
    if background:
        ctx += f"\n\n【背景前提】\n{background}"
    return ctx


def _build_all_stances_summary(debate_id: str) -> str:
    """所有方立论摘要（观点 + 有效事实，不含论据全文）。"""
    parties = debate_store.get_parties(debate_id)
    parts = []
    for p in parties:
        stance_data = storage.read_stance(debate_id, p.party_id)
        if not stance_data:
            continue
        viewpoint = stance_data.get("viewpoint", "")
        facts = stance_data.get("facts", "")
        valid_facts = [l for l in facts.strip().split("\n") if l.strip() and not l.strip().startswith("[假]")]
        section = f"【{p.name}（{p.party_id}）】\n观点：{viewpoint}"
        if valid_facts:
            section += f"\n有效事实（{len(valid_facts)}条）：\n" + "\n".join(f"  - {f}" for f in valid_facts[:10])
        parts.append(section)
    return "\n\n".join(parts)


def _build_round_solutions_context(debate_id: str, round_num: int) -> str:
    """本轮各方解决方案。"""
    solutions = debate_store.get_round_solutions(debate_id, round_num)
    if not solutions:
        return f"（第{round_num}轮尚无解决方案）"
    parts = []
    for sol in solutions:
        party = debate_store.get_party(debate_id, sol.party_id)
        name = party.name if party else sol.party_id
        parts.append(f"【{name}（{sol.party_id}）的方案】\n{sol.content}")
    return "\n\n".join(parts)


def _get_locked_consensus(debate_id: str, up_to_round: int) -> str:
    """获取截至指定轮次的累积锁定共识。"""
    # 从最近一轮的 judge_summary 中获取 locked_consensus
    for r in range(up_to_round - 1, 0, -1):
        summary = debate_store.get_judge_summary(debate_id, r)
        if summary and summary.locked_consensus:
            return summary.locked_consensus
    return ""


# ── 工具集 ────────────────────────────────────────────────

def _make_judge_tools(debate_id: str):
    """裁判工具集：保留写入类工具，读取由上下文注入。"""

    @tool
    def read_stance_detail(party_id: str) -> str:
        """读取指定方的完整立论（需要深入检查合规性时使用）。"""
        data = storage.read_stance(debate_id, party_id)
        if not data:
            return f"{party_id} 的立论不存在。"
        return json.dumps(data, ensure_ascii=False, indent=2)

    @tool
    def mark_solution_validity(round_num: int, party_id: str, is_valid: bool, reason: str = "") -> str:
        """标记某方解决方案的有效性。"""
        sol = debate_store.get_solution(debate_id, round_num, party_id)
        if not sol:
            return f"解决方案不存在（round={round_num}, party={party_id}）。"
        sol.is_valid = is_valid
        sol.invalid_reason = reason
        debate_store.save_solution(sol)
        return f"已标记 {party_id} 第 {round_num} 轮方案有效性为 {is_valid}。"

    @tool
    def write_judge_summary(
        round_num: int,
        consensus: str,
        contradictions: str,
        combined_solution: str,
        has_contradiction: bool,
        focus_next: str = "",
        locked_consensus: str = "",
    ) -> str:
        """写入裁判梳理结果。focus_next 为下一轮聚焦指令，locked_consensus 为累积锁定共识。"""
        summary = JudgeSummary(
            summary_id=str(uuid.uuid4()),
            debate_id=debate_id,
            round=round_num,
            consensus=consensus,
            contradictions=contradictions,
            combined_solution=combined_solution,
            has_contradiction=has_contradiction,
            focus_next=focus_next,
            locked_consensus=locked_consensus,
            created_at=datetime.now(timezone.utc),
        )
        debate_store.save_judge_summary(summary)
        return f"裁判梳理结果已保存（round={round_num}，has_contradiction={has_contradiction}）。"

    return [
        read_stance_detail,
        mark_solution_validity,
        write_judge_summary,
    ]


# ── JudgeAgent 主类 ───────────────────────────────────────

class JudgeAgent:
    """裁判 Agent 封装。无状态模式。"""

    def __init__(self, debate_id: str):
        self.debate_id = debate_id

    def _create_agent(self, system_context: str):
        """创建无状态 agent。"""
        tools = _make_judge_tools(self.debate_id)
        llm = _get_llm()
        full_prompt = _JUDGE_RULES + "\n\n---\n\n" + system_context
        return create_react_agent(
            model=llm,
            tools=tools,
            prompt=full_prompt,
        )

    def run_round_review(self, round_num: int) -> str:
        """执行本轮裁判梳理：有效性 + 合规性 + 共识锁定 + 矛盾排序 + 收敛引导。"""
        locked = _get_locked_consensus(self.debate_id, round_num)

        context_parts = [
            _build_judge_proposition_context(self.debate_id),
            _build_all_stances_summary(self.debate_id),
            f"【第{round_num}轮各方解决方案】\n" + _build_round_solutions_context(self.debate_id, round_num),
        ]
        if locked:
            context_parts.insert(1, f"【已锁定共识（不可推翻）】\n{locked}")

        system_context = "\n\n".join(p for p in context_parts if p)
        agent = self._create_agent(system_context)

        prompt = (
            f"请对第 {round_num} 轮各方解决方案进行完整裁判梳理：\n\n"
            f"1. 有效性检查：方案是否围绕命题展开，调用 mark_solution_validity 标记\n"
            f"2. 合规性检查：方案是否违背己方事实或已锁定共识\n"
            f"3. 共识提取：找出本轮各方均认可的内容，与已锁定共识合并\n"
            f"4. 矛盾提取：找出分歧点，按对最终可实施方案的影响程度排序\n"
            f"5. 收敛引导：在 focus_next 中指定下一轮必须优先解决的第一矛盾，"
            f"具体说明矛盾焦点和各方分歧，要求各方提出针对性折中方案\n"
            f"6. 调用 write_judge_summary 保存，确保填写 focus_next 和 locked_consensus"
        )
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        return result["messages"][-1].content

    def run_final_verdict_no_contradiction(self, round_num: int) -> str:
        """无矛盾终论。"""
        locked = _get_locked_consensus(self.debate_id, round_num)

        context_parts = [
            _build_judge_proposition_context(self.debate_id),
            _build_round_solutions_context(self.debate_id, round_num),
        ]
        if locked:
            context_parts.insert(1, f"【已锁定共识】\n{locked}")

        system_context = "\n\n".join(p for p in context_parts if p)
        agent = self._create_agent(system_context)

        prompt = (
            f"第 {round_num} 轮裁判梳理显示无矛盾。请综合各方解决方案和已锁定共识，"
            f"给出唯一最终解决方案。方案须具体、可落地、可执行。\n"
            f"调用 write_judge_summary 保存（has_contradiction=False）。"
        )
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        return result["messages"][-1].content

    def run_final_verdict_max_rounds(self, round_num: int) -> str:
        """满 5 轮终论。"""
        locked = _get_locked_consensus(self.debate_id, round_num)

        context_parts = [
            _build_judge_proposition_context(self.debate_id),
            _build_round_solutions_context(self.debate_id, round_num),
        ]
        if locked:
            context_parts.insert(1, f"【已锁定共识】\n{locked}")

        system_context = "\n\n".join(p for p in context_parts if p)
        agent = self._create_agent(system_context)

        prompt = (
            f"辩论已满 5 轮（当前第 {round_num} 轮）。请读取各方最终解决方案，"
            f"结合已锁定共识，选出实现方式最简单、代价最小的方案作为唯一最终方案，"
            f"并在 combined_solution 中附上选择理由简述。\n"
            f"调用 write_judge_summary 保存结果。"
        )
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        return result["messages"][-1].content
