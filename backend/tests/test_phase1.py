"""
阶段一单元测试：storage.py 和 config.py
"""

import json
import sys
import tempfile
from pathlib import Path

# 将 backend 加入路径
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── storage.py 测试 ────────────────────────────────────────

def test_path_generation():
    """验证路径生成规则与需求文档第 6 节目录结构一致。"""
    from services import storage

    # 临时替换 _BASE
    orig_base = storage._BASE
    with tempfile.TemporaryDirectory() as tmp:
        storage._BASE = Path(tmp)

        d = "debate_abc"
        p = "party_x"
        r = 2

        assert storage.debate_state_path(d) == Path(tmp) / d / "debate_state.json"
        assert storage.proposition_path(d) == Path(tmp) / d / "proposition.json"
        assert storage.stance_path(d, p) == Path(tmp) / d / "parties" / p / "stance.json"
        assert storage.changelogs_path(d, p) == Path(tmp) / d / "parties" / p / "changelogs.json"
        assert storage.round_state_path(d, r) == Path(tmp) / d / "rounds" / "2" / "round_state.json"
        assert storage.solution_path(d, r, p) == Path(tmp) / d / "rounds" / "2" / "solutions" / f"{p}_solution.json"
        assert storage.judge_summary_path(d, r) == Path(tmp) / d / "rounds" / "2" / "judge_summary.json"
        assert storage.challenge_path(d, r, p) == Path(tmp) / d / "rounds" / "2" / "debates" / f"{p}_challenge.json"
        assert storage.reflection_path(d, r, p) == Path(tmp) / d / "rounds" / "2" / "debates" / f"{p}_reflection.json"

        storage._BASE = orig_base
    print("PASS: path_generation")


def test_json_read_write():
    """验证 JSON 读写正确性。"""
    from services import storage

    orig_base = storage._BASE
    with tempfile.TemporaryDirectory() as tmp:
        storage._BASE = Path(tmp)

        data = {"key": "value", "num": 42, "list": [1, 2, 3]}
        storage.write_debate_state("d1", data)
        result = storage.read_debate_state("d1")
        assert result == data, f"Expected {data}, got {result}"

        storage._BASE = orig_base
    print("PASS: json_read_write")


def test_auto_create_dirs():
    """验证不存在的路径能自动创建。"""
    from services import storage

    orig_base = storage._BASE
    with tempfile.TemporaryDirectory() as tmp:
        storage._BASE = Path(tmp)

        # 写入深层路径，父目录不存在
        storage.write_solution("d1", 3, "party_a", {"content": "test"})
        path = storage.solution_path("d1", 3, "party_a")
        assert path.exists(), f"File not created: {path}"

        storage._BASE = orig_base
    print("PASS: auto_create_dirs")


def test_read_nonexistent_returns_none():
    """验证读取不存在的文件返回 None（changelogs 返回空列表）。"""
    from services import storage

    orig_base = storage._BASE
    with tempfile.TemporaryDirectory() as tmp:
        storage._BASE = Path(tmp)

        assert storage.read_debate_state("no_such") is None
        assert storage.read_changelogs("no_such", "no_party") == []

        storage._BASE = orig_base
    print("PASS: read_nonexistent_returns_none")


def test_list_debate_ids():
    """验证 list_debate_ids 只返回有 debate_state.json 的目录。"""
    from services import storage

    orig_base = storage._BASE
    with tempfile.TemporaryDirectory() as tmp:
        storage._BASE = Path(tmp)

        storage.write_debate_state("d1", {"debate_id": "d1"})
        storage.write_debate_state("d2", {"debate_id": "d2"})
        # 创建一个没有 debate_state.json 的目录
        (Path(tmp) / "d3").mkdir()

        ids = storage.list_debate_ids()
        assert set(ids) == {"d1", "d2"}, f"Expected {{d1, d2}}, got {ids}"

        storage._BASE = orig_base
    print("PASS: list_debate_ids")


# ── config.py 测试 ─────────────────────────────────────────

def test_config_read_write():
    """验证配置读写、KEY 字段存储与读取正确。"""
    import config

    orig_path = config._CONFIG_PATH
    with tempfile.TemporaryDirectory() as tmp:
        config._CONFIG_PATH = Path(tmp) / "config.json"

        config.write_config("https://api.example.com", "sk-test-key-1234")
        result = config.read_config()
        assert result["api_url"] == "https://api.example.com"
        assert result["api_key"] == "sk-test-key-1234"

        config._CONFIG_PATH = orig_path
    print("PASS: config_read_write")


def test_config_default_when_missing():
    """验证配置文件不存在时返回默认值。"""
    import config

    orig_path = config._CONFIG_PATH
    with tempfile.TemporaryDirectory() as tmp:
        config._CONFIG_PATH = Path(tmp) / "nonexistent.json"

        result = config.read_config()
        assert result["api_url"] == ""
        assert result["api_key"] == ""

        config._CONFIG_PATH = orig_path
    print("PASS: config_default_when_missing")


def test_mask_key():
    """验证 KEY 脱敏逻辑。"""
    import config

    assert config.mask_key("sk-abcdefgh1234") == "sk-a****1234"
    assert config.mask_key("short") == "****"
    assert config.mask_key("12345678") == "****"  # 恰好 8 位
    assert config.mask_key("123456789") == "1234****6789"  # 9 位
    print("PASS: mask_key")


if __name__ == "__main__":
    test_path_generation()
    test_json_read_write()
    test_auto_create_dirs()
    test_read_nonexistent_returns_none()
    test_list_debate_ids()
    test_config_read_write()
    test_config_default_when_missing()
    test_mask_key()
    print("\n所有阶段一测试通过。")
