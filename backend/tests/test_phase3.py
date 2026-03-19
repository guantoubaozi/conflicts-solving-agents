"""
阶段三单元测试：后端 API
"""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient


def _make_client(tmp_dir: str):
    """创建隔离的测试客户端，使用临时目录。"""
    import services.storage as storage
    import config as cfg

    storage._BASE = Path(tmp_dir) / "debates"
    cfg._CONFIG_PATH = Path(tmp_dir) / "config.json"

    from main import app
    return TestClient(app)


def test_config_api():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        # PUT 保存配置
        r = client.put("/api/config", json={"api_url": "https://api.test.com", "api_key": "sk-abcdefgh1234"})
        assert r.status_code == 200

        # GET 返回脱敏 KEY
        r = client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert data["api_url"] == "https://api.test.com"
        assert "sk-a" in data["api_key_masked"]
        assert "sk-abcdefgh1234" not in data["api_key_masked"]
    print("PASS: config_api")


def test_create_debate():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        r = client.post("/api/debates", json={"proposition": "测试命题", "created_by": "user1"})
        assert r.status_code == 200
        data = r.json()
        assert "debate_id" in data
        assert "proposition_id" in data

        # 持久化文件已生成
        debate_dir = Path(tmp) / "debates" / data["debate_id"]
        assert (debate_dir / "debate_state.json").exists()
        assert (debate_dir / "proposition.json").exists()
    print("PASS: create_debate")


def test_list_debates():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        client.post("/api/debates", json={"proposition": "命题A"})
        client.post("/api/debates", json={"proposition": "命题B"})

        r = client.get("/api/debates")
        assert r.status_code == 200
        assert len(r.json()) == 2
    print("PASS: list_debates")


def test_add_party_and_list():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        r = client.post("/api/debates", json={"proposition": "命题"})
        debate_id = r.json()["debate_id"]

        r = client.post(f"/api/debates/{debate_id}/parties", json={"name": "甲方"})
        assert r.status_code == 200
        party_id = r.json()["party_id"]

        r = client.get(f"/api/debates/{debate_id}/parties")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["name"] == "甲方"

        # 辩论状态应已变为 STANCE
        r = client.get(f"/api/debates/{debate_id}")
        assert r.json()["status"] == "STANCE"
    print("PASS: add_party_and_list")


def test_submit_stance_validation():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        r = client.post("/api/debates", json={"proposition": "命题"})
        debate_id = r.json()["debate_id"]
        r = client.post(f"/api/debates/{debate_id}/parties", json={"name": "甲方"})
        party_id = r.json()["party_id"]

        # 观点超 200 字应报错
        long_viewpoint = "观" * 201
        r = client.post(
            f"/api/debates/{debate_id}/parties/{party_id}/stance",
            json={"viewpoint": long_viewpoint},
        )
        assert r.status_code == 422

        # 事实超 1000 字应报错
        long_facts = "事" * 1001
        r = client.post(
            f"/api/debates/{debate_id}/parties/{party_id}/stance",
            json={"viewpoint": "正常观点", "facts": long_facts},
        )
        assert r.status_code == 422

        # 正常提交
        r = client.post(
            f"/api/debates/{debate_id}/parties/{party_id}/stance",
            json={"viewpoint": "我方观点", "facts": "事实内容"},
        )
        assert r.status_code == 200
    print("PASS: submit_stance_validation")


def test_start_debate():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        r = client.post("/api/debates", json={"proposition": "命题"})
        debate_id = r.json()["debate_id"]
        r = client.post(f"/api/debates/{debate_id}/parties", json={"name": "甲方"})
        party_id = r.json()["party_id"]

        # 未提交立论时不能开始
        r = client.post(f"/api/debates/{debate_id}/start")
        assert r.status_code == 400

        # 提交立论后可以开始
        client.post(
            f"/api/debates/{debate_id}/parties/{party_id}/stance",
            json={"viewpoint": "观点"},
        )
        r = client.post(f"/api/debates/{debate_id}/start")
        assert r.status_code == 200
        assert r.json()["status"] == "ROUND"
    print("PASS: start_debate")


def test_submit_solution_phase_check():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        r = client.post("/api/debates", json={"proposition": "命题"})
        debate_id = r.json()["debate_id"]
        r = client.post(f"/api/debates/{debate_id}/parties", json={"name": "甲方"})
        party_id = r.json()["party_id"]
        client.post(
            f"/api/debates/{debate_id}/parties/{party_id}/stance",
            json={"viewpoint": "观点"},
        )
        client.post(f"/api/debates/{debate_id}/start")

        # 正确轮次可提交
        r = client.post(
            f"/api/debates/{debate_id}/rounds/1/solutions",
            json={"party_id": party_id, "content": "方案内容"},
        )
        assert r.status_code == 200

        # 错误轮次拒绝
        r = client.post(
            f"/api/debates/{debate_id}/rounds/2/solutions",
            json={"party_id": party_id, "content": "方案内容"},
        )
        assert r.status_code == 400
    print("PASS: submit_solution_phase_check")


def test_human_confirm_flow():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        r = client.post("/api/debates", json={"proposition": "命题"})
        debate_id = r.json()["debate_id"]
        r = client.post(f"/api/debates/{debate_id}/parties", json={"name": "甲方"})
        party_a = r.json()["party_id"]
        r = client.post(f"/api/debates/{debate_id}/parties", json={"name": "乙方"})
        party_b = r.json()["party_id"]

        for pid in [party_a, party_b]:
            client.post(
                f"/api/debates/{debate_id}/parties/{pid}/stance",
                json={"viewpoint": "观点"},
            )
        client.post(f"/api/debates/{debate_id}/start")

        # 手动将轮次状态推进到 HUMAN_REVIEW（正常由 Agent 触发，这里直接写文件模拟）
        from services import debate_store
        from models.debate_round import RoundPhase
        rs = debate_store.get_round_state(debate_id, 1)
        rs.status = RoundPhase.HUMAN_REVIEW
        debate_store.save_round_state(rs)

        # 甲方确认，未全员
        r = client.post(f"/api/debates/{debate_id}/rounds/1/confirm?party_id={party_a}")
        assert r.status_code == 200
        assert r.json()["all_confirmed"] is False

        # 乙方确认，全员确认，推进到第 2 轮
        r = client.post(f"/api/debates/{debate_id}/rounds/1/confirm?party_id={party_b}")
        assert r.status_code == 200
        assert r.json()["all_confirmed"] is True

        r = client.get(f"/api/debates/{debate_id}")
        assert r.json()["current_round"] == 2
    print("PASS: human_confirm_flow")


def test_sse_connect():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)

        r = client.post("/api/debates", json={"proposition": "命题"})
        debate_id = r.json()["debate_id"]

        # SSE 连接不报错（TestClient 会立即断开）
        with client.stream("GET", f"/api/debates/{debate_id}/stream") as resp:
            assert resp.status_code == 200
    print("PASS: sse_connect")


if __name__ == "__main__":
    test_config_api()
    test_create_debate()
    test_list_debates()
    test_add_party_and_list()
    test_submit_stance_validation()
    test_start_debate()
    test_submit_solution_phase_check()
    test_human_confirm_flow()
    test_sse_connect()
    print("\n所有阶段三测试通过。")
