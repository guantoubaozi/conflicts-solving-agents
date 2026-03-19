"""
config.py — AI 模型配置读写

配置存储在项目根目录的 config.json：
{
  "api_url": "https://...",
  "api_key": "sk-..."
}
"""

import json
import os
from pathlib import Path

_CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", str(Path(__file__).parent.parent / "config.json")))

_DEFAULT: dict = {
    "api_url": "",
    "api_key": "",
    "model_name": "gpt-4o",
}


def read_config() -> dict:
    """读取配置，文件不存在时返回默认值。"""
    if not _CONFIG_PATH.exists():
        return dict(_DEFAULT)
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 补全缺失字段
    for k, v in _DEFAULT.items():
        data.setdefault(k, v)
    return data


def write_config(api_url: str, api_key: str, model_name: str = "gpt-4o") -> None:
    """写入配置。api_key 为空时保留已有 key。"""
    existing = read_config()
    data = {
        "api_url": api_url,
        "api_key": api_key if api_key else existing["api_key"],
        "model_name": model_name,
    }
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def mask_key(api_key: str) -> str:
    """脱敏处理：保留前 4 位和后 4 位，中间替换为 ****。"""
    if len(api_key) <= 8:
        return "****"
    return api_key[:4] + "****" + api_key[-4:]
