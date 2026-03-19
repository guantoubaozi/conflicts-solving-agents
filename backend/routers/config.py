"""
routers/config.py — AI 模型配置接口
"""

from fastapi import APIRouter
from pydantic import BaseModel

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config as cfg

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigIn(BaseModel):
    api_url: str
    api_key: str
    model_name: str = "gpt-4o"


class ConfigOut(BaseModel):
    api_url: str
    api_key_masked: str
    model_name: str


@router.get("", response_model=ConfigOut)
def get_config():
    data = cfg.read_config()
    return ConfigOut(api_url=data["api_url"], api_key_masked=cfg.mask_key(data["api_key"]), model_name=data["model_name"])


@router.put("")
def put_config(body: ConfigIn):
    cfg.write_config(body.api_url, body.api_key, body.model_name)
    return {"ok": True}
