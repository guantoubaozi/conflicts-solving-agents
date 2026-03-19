"""
main.py — FastAPI 入口
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import config, debates, parties, stances, solutions, changelogs, stream

app = FastAPI(title="争端解决仪", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router)
app.include_router(debates.router)
app.include_router(parties.router)
app.include_router(stances.router)
app.include_router(solutions.router)
app.include_router(changelogs.router)
app.include_router(stream.router)


@app.on_event("startup")
async def startup_event():
    """服务启动时扫描 debates/ 目录，记录未完成的辩论场次（不自动恢复执行，等待前端触发）。"""
    from services.debate_service import recover_debates
    unfinished = recover_debates()
    if unfinished:
        print(f"[startup] 发现 {len(unfinished)} 个未完成的辩论场次: {unfinished}")


@app.get("/health")
def health():
    return {"status": "ok"}
