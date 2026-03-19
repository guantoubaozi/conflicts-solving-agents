"""
storage.py — 文件持久化读写工具

目录结构（需求文档第 6 节）：
debates/
└── {debate_id}/
    ├── debate_state.json
    ├── proposition.json
    ├── parties/
    │   └── {party_id}/
    │       ├── stance.json
    │       └── changelogs.json
    └── rounds/
        └── {round}/
            ├── round_state.json
            ├── solutions/
            │   └── {party_id}_solution.json
            ├── judge_summary.json
            └── debates/
                ├── {party_id}_challenge.json
                └── {party_id}_reflection.json
"""

import json
import os
from pathlib import Path
from typing import Any

# 运行时数据根目录：优先读取环境变量 DEBATES_BASE
_BASE = Path(os.environ.get("DEBATES_BASE", str(Path(__file__).parent.parent / "debates")))


def _ensure(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ── 路径生成 ──────────────────────────────────────────────

def debate_dir(debate_id: str) -> Path:
    return _BASE / debate_id


def debate_state_path(debate_id: str) -> Path:
    return debate_dir(debate_id) / "debate_state.json"


def proposition_path(debate_id: str) -> Path:
    return debate_dir(debate_id) / "proposition.json"


def party_dir(debate_id: str, party_id: str) -> Path:
    return debate_dir(debate_id) / "parties" / party_id


def stance_path(debate_id: str, party_id: str) -> Path:
    return party_dir(debate_id, party_id) / "stance.json"


def changelogs_path(debate_id: str, party_id: str) -> Path:
    return party_dir(debate_id, party_id) / "changelogs.json"


def round_dir(debate_id: str, round_num: int) -> Path:
    return debate_dir(debate_id) / "rounds" / str(round_num)


def round_state_path(debate_id: str, round_num: int) -> Path:
    return round_dir(debate_id, round_num) / "round_state.json"


def solution_path(debate_id: str, round_num: int, party_id: str) -> Path:
    return round_dir(debate_id, round_num) / "solutions" / f"{party_id}_solution.json"


def judge_summary_path(debate_id: str, round_num: int) -> Path:
    return round_dir(debate_id, round_num) / "judge_summary.json"


def challenge_path(debate_id: str, round_num: int, party_id: str) -> Path:
    return round_dir(debate_id, round_num) / "debates" / f"{party_id}_challenge.json"


def reflection_path(debate_id: str, round_num: int, party_id: str) -> Path:
    return round_dir(debate_id, round_num) / "debates" / f"{party_id}_reflection.json"


# ── JSON 读写 ─────────────────────────────────────────────

def read_json(path: Path) -> Any:
    """读取 JSON 文件，文件不存在时返回 None。"""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    """写入 JSON 文件，自动创建父目录。"""
    _ensure(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 便捷封装 ──────────────────────────────────────────────

def read_debate_state(debate_id: str) -> dict | None:
    return read_json(debate_state_path(debate_id))


def write_debate_state(debate_id: str, data: dict) -> None:
    write_json(debate_state_path(debate_id), data)


def read_proposition(debate_id: str) -> dict | None:
    return read_json(proposition_path(debate_id))


def write_proposition(debate_id: str, data: dict) -> None:
    write_json(proposition_path(debate_id), data)


def read_stance(debate_id: str, party_id: str) -> dict | None:
    return read_json(stance_path(debate_id, party_id))


def write_stance(debate_id: str, party_id: str, data: dict) -> None:
    write_json(stance_path(debate_id, party_id), data)


def read_changelogs(debate_id: str, party_id: str) -> list:
    data = read_json(changelogs_path(debate_id, party_id))
    return data if data is not None else []


def write_changelogs(debate_id: str, party_id: str, data: list) -> None:
    write_json(changelogs_path(debate_id, party_id), data)


def read_round_state(debate_id: str, round_num: int) -> dict | None:
    return read_json(round_state_path(debate_id, round_num))


def write_round_state(debate_id: str, round_num: int, data: dict) -> None:
    write_json(round_state_path(debate_id, round_num), data)


def read_solution(debate_id: str, round_num: int, party_id: str) -> dict | None:
    return read_json(solution_path(debate_id, round_num, party_id))


def write_solution(debate_id: str, round_num: int, party_id: str, data: dict) -> None:
    write_json(solution_path(debate_id, round_num, party_id), data)


def read_judge_summary(debate_id: str, round_num: int) -> dict | None:
    return read_json(judge_summary_path(debate_id, round_num))


def write_judge_summary(debate_id: str, round_num: int, data: dict) -> None:
    write_json(judge_summary_path(debate_id, round_num), data)


def read_challenge(debate_id: str, round_num: int, party_id: str) -> dict | None:
    return read_json(challenge_path(debate_id, round_num, party_id))


def write_challenge(debate_id: str, round_num: int, party_id: str, data: dict) -> None:
    write_json(challenge_path(debate_id, round_num, party_id), data)


def read_reflection(debate_id: str, round_num: int, party_id: str) -> dict | None:
    return read_json(reflection_path(debate_id, round_num, party_id))


def write_reflection(debate_id: str, round_num: int, party_id: str, data: dict) -> None:
    write_json(reflection_path(debate_id, round_num, party_id), data)


def delete_debate_dir(debate_id: str) -> bool:
    """删除整个辩论目录，返回是否成功。"""
    import shutil
    d = debate_dir(debate_id)
    if d.exists():
        shutil.rmtree(d)
        return True
    return False


def list_debate_ids() -> list[str]:
    """扫描 debates/ 目录，返回所有 debate_id 列表。"""
    if not _BASE.exists():
        return []
    return [
        d.name for d in _BASE.iterdir()
        if d.is_dir() and (d / "debate_state.json").exists()
    ]
