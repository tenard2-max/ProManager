"""관제 에이전트 FastAPI 서버. 127.0.0.1 전용."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app import config as app_config
from app.config import (
    HOST,
    PORT,
    STATIC_DIR,
    TOKEN_LIVE_INTERVAL_SEC,
    ensure_dirs,
)
from app.history.log import HistoryLog
from app.ini.spec_parser import parse_spec_ini
from app.ini.status_store import StatusStore
from app.messaging.command import CommandDispatcher
from app.messaging.heartbeat import HeartbeatTracker
from app.messaging.inbox import MessageInbox
from app.metrics.calculator import MetricsCalculator
from app.models.messages import CommandRequest
from app.tokens.cursor_live import CursorLiveUsageClient
from app.tokens.usage import TokenUsageStore
from app.watch.loop import WatchLoop

ensure_dirs()

status_store = StatusStore()
history = HistoryLog()
heartbeat = HeartbeatTracker()
metrics = MetricsCalculator(status_store, history)
commands = CommandDispatcher(status_store, history)
token_store = TokenUsageStore()
cursor_live = CursorLiveUsageClient()
_live_task: asyncio.Task | None = None
_last_live_sync_at = 0.0


def sync_cursor_usage(*, force: bool = False) -> dict[str, Any]:
    """Cursor Dashboard API에서 주 사용량을 가져와 저장소에 반영."""
    global _last_live_sync_at
    now = time.monotonic()
    if not force and (now - _last_live_sync_at) < 3.0:
        return token_store.snapshot(reload_disk=True)
    live = cursor_live.fetch()
    _last_live_sync_at = now
    if live is None:
        err = cursor_live.last_error or "Cursor 사용량 조회 실패"
        history.append("token_live_error", {"error": err})
        return token_store.apply_live({}, error=err)
    history.append(
        "token_live_sync",
        {
            "used_hint": live.get("live_total_percent"),
            "plan": live.get("plan"),
            "renews_at": live.get("renews_at"),
        },
    )
    return token_store.apply_live(live)


async def _live_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(sync_cursor_usage, force=True)
        except Exception as exc:  # noqa: BLE001
            history.append("token_live_loop_error", {"error": str(exc)})
        await asyncio.sleep(TOKEN_LIVE_INTERVAL_SEC)


def _write_spec(text: str) -> None:
    path = Path(app_config.SPEC_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


inbox = MessageInbox(
    status_store,
    history,
    heartbeat,
    command_ack_handler=commands.handle_ack,
    spec_writer=_write_spec,
    token_store=token_store,
)

watch = WatchLoop(
    status_store,
    history,
    heartbeat_checker=heartbeat.status_map,
    metrics_calculator=metrics.calculate,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 시작 시 기존 파일 로드
    if Path(app_config.SPEC_PATH).exists():
        try:
            spec = parse_spec_ini(app_config.SPEC_PATH, strict=False)
            if status_store.path.exists():
                status_store.load()
            else:
                status_store.apply_spec_reset(spec, updated_by="agent")
            # 명세 부가 필드를 상태에 병합
            if status_store.document:
                for rid, sitem in spec.items.items():
                    if rid in status_store.document.items:
                        item = status_store.document.items[rid]
                        item.priority = sitem.priority
                        item.spec_ref = sitem.spec_ref
                        item.acceptance_criteria = sitem.acceptance_criteria
                        item.target_files = sitem.target_files
        except Exception as exc:  # noqa: BLE001
            history.append("startup_spec_error", {"error": str(exc)})
    elif status_store.path.exists():
        status_store.load()

    await watch.start()
    global _live_task
    # 기동 직후 1회 동기화 + 10초 주기 백그라운드 동기화
    await asyncio.to_thread(sync_cursor_usage, force=True)
    _live_task = asyncio.create_task(_live_loop())
    yield
    if _live_task:
        _live_task.cancel()
        try:
            await _live_task
        except asyncio.CancelledError:
            pass
        _live_task = None
    await watch.stop()


app = FastAPI(title="Agent Monitor", lifespan=lifespan)


@app.post("/api/messages")
async def post_message(body: dict[str, Any]) -> dict[str, Any]:
    return inbox.handle(body)


@app.get("/api/messages/outbox")
async def get_outbox(agent: str = Query(..., pattern="^(cursor|grok)$")) -> dict[str, Any]:
    return {"messages": commands.poll_outbox(agent)}


@app.post("/api/commands")
async def post_command(req: CommandRequest) -> dict[str, Any]:
    try:
        tracked = commands.submit(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 상태 파일 해시가 바뀌도록 watch가 다음 tick에 감지
    return tracked.to_dict()


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    doc = status_store.document
    items = []
    categories: dict[str, list[int]] = {}
    status_counts = {
        "TODO": 0,
        "IN_PROGRESS": 0,
        "IN_REVIEW": 0,
        "REWORK_REQUESTED": 0,
        "VERIFIED": 0,
    }
    cursor_cats: dict[str, list[float]] = {}
    grok_cats: dict[str, list[float]] = {}
    if doc:
        for item in doc.items.values():
            d = item.to_dict()
            items.append(d)
            categories.setdefault(item.category, []).append(item.progress)
            if item.status in status_counts:
                status_counts[item.status] += 1
            # Cursor 구간: 0~60 (상한 60을 100%로 환산해 표시)
            cursor_raw = min(max(int(item.progress), 0), 60)
            cursor_cats.setdefault(item.category, []).append(
                round(100.0 * cursor_raw / 60.0, 2)
            )
            # Grok 구간: QA 점수 우선, 없으면 progress 80+만 반영
            if item.qa_status == "PASSED" or item.status == "VERIFIED":
                grok_val = float(item.qa_score)
            elif int(item.progress) >= 80:
                grok_val = max(0.0, min(100.0, (int(item.progress) - 80) / 0.2))
            else:
                grok_val = 0.0
            grok_cats.setdefault(item.category, []).append(round(grok_val, 2))

    def _avg(mapping: dict[str, list[float]]) -> dict[str, float]:
        return {
            cat: round(sum(vals) / len(vals), 2) if vals else 0.0
            for cat, vals in mapping.items()
        }

    category_bars = _avg({k: [float(x) for x in v] for k, v in categories.items()})
    category_progress_cursor = _avg(cursor_cats)
    category_progress_grok = _avg(grok_cats)

    return {
        "meta": doc.meta if doc else {},
        "items": items,
        "status_counts": status_counts,
        "category_progress": category_bars,
        "category_progress_cursor": category_progress_cursor,
        "category_progress_grok": category_progress_grok,
        "metrics": metrics.calculate(),
        "watch": watch.snapshot_public(),
        "commands": commands.list_commands(20),
        "agents": heartbeat.detail(),
        "tokens": token_store.snapshot(reload_disk=True),
    }


@app.get("/api/tokens")
async def get_tokens(response: Response) -> dict[str, Any]:
    # 브라우저/중간 캐시 금지 — 10초 폴링이 항상 최신을 받도록
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    # 백그라운드 루프와 별도로, 요청 시에도 stale이면 동기화
    return await asyncio.to_thread(sync_cursor_usage, force=False)


@app.post("/api/tokens")
async def post_tokens(body: dict[str, Any]) -> dict[str, Any]:
    try:
        used_pct = body.get("used_pct")
        cursor_share = body.get("cursor_share")
        return token_store.update(
            cursor_used=body.get("cursor_used"),
            grok_used=body.get("grok_used"),
            weekly_included=body.get("weekly_included"),
            plan=body.get("plan"),
            renews_at=body.get("renews_at"),
            period_start=body.get("period_start"),
            cycle_weeks=body.get("cycle_weeks"),
            used_pct=float(used_pct) if used_pct is not None else None,
            cursor_share=float(cursor_share) if cursor_share is not None else None,
            cursor_delta=int(body.get("cursor_delta", 0) or 0),
            grok_delta=int(body.get("grok_delta", 0) or 0),
            source=str(body.get("source", "ui" if used_pct is not None else "api")),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/history")
async def get_history(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    return {"events": history.read_all(limit=limit)}


@app.get("/api/metrics")
async def get_metrics(recalc: bool = False) -> dict[str, Any]:
    if recalc:
        return metrics.recalculate_from_history()
    return metrics.calculate()


@app.get("/")
async def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI 없음")
    return FileResponse(index_path)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
    )


if __name__ == "__main__":
    run()
