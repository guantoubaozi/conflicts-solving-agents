"""
routers/stream.py — SSE 实时推送接口
"""

import asyncio
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import debate_store

router = APIRouter(prefix="/api/debates", tags=["stream"])

# 全局事件队列：debate_id -> list of asyncio.Queue
_queues: dict[str, list[asyncio.Queue]] = {}


def get_queues(debate_id: str) -> list[asyncio.Queue]:
    return _queues.get(debate_id, [])


async def push_event(debate_id: str, event_type: str, data: dict) -> None:
    """向指定辩论的所有 SSE 订阅者推送事件。"""
    import json
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
    for q in list(_queues.get(debate_id, [])):
        await q.put(payload)


@router.get("/{debate_id}/stream")
async def stream(debate_id: str, request: Request):
    debate = debate_store.get_debate(debate_id)
    if not debate:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="debate not found")

    queue: asyncio.Queue = asyncio.Queue()
    _queues.setdefault(debate_id, []).append(queue)

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"data": data}
                except asyncio.TimeoutError:
                    yield {"data": '{"type":"ping"}'}
        finally:
            _queues[debate_id].remove(queue)

    return EventSourceResponse(generator())
