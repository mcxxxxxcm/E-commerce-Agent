"""
电商运营 Agent 服务入口
架构: Deep Agent + 定时任务调度
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.config import get_settings
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger, setup_logging
from shared.tools.registry import get_tools_by_tags
from shared.tracing import init_tracing, instrument_app

from .agent import create_ops_agent

logger = get_logger(__name__)

_settings = get_settings()
_event_bus: EventBus | None = None
_agent = None
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _agent, _scheduler

    setup_logging(service_name="operations", log_level=_settings.log_level)

    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()
    await _event_bus.start()

    # 获取运营专用工具
    ops_tools = get_tools_by_tags(["analytics", "product", "competitor", "report"])
    _agent = create_ops_agent(ops_tools)

    # 启动定时任务
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    _scheduler = AsyncIOScheduler()

    from .tasks.daily_report import daily_report_task
    from .tasks.weekly_analysis import weekly_analysis_task

    _scheduler.add_job(
        lambda: daily_report_task(_agent, _event_bus),
        "cron",
        hour=9,
        minute=5,
        id="daily_report",
    )
    _scheduler.add_job(
        lambda: weekly_analysis_task(_agent, _event_bus),
        "cron",
        day_of_week="mon",
        hour=9,
        minute=15,
        id="weekly_analysis",
    )
    _scheduler.start()

    logger.info("operations.started")
    yield

    if _scheduler:
        _scheduler.shutdown()
    await _event_bus.disconnect()
    logger.info("operations.stopped")


app = FastAPI(title="Operations Agent", version="0.1.0", lifespan=lifespan)
tracer = init_tracing("operations", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "operations")


class AnalysisRequest(BaseModel):
    task: str
    context: dict[str, Any] = {}


class AnalysisResponse(BaseModel):
    result: str
    actions_taken: list[str]


@app.get("/health")
async def health() -> dict:
    return {"service": "operations", "status": "healthy"}


@app.post("/analyze")
async def analyze(request: AnalysisRequest) -> dict:
    """执行运营分析任务 — 自主规划型"""
    try:
        result = await _agent.ainvoke({
            "messages": [
                {
                    "role": "user",
                    "content": request.task,
                }
            ]
        })

        last_msg = result.get("messages", [{}])[-1]
        return {
            "result": last_msg.get("content", ""),
            "actions_taken": [],
        }

    except Exception as exc:
        logger.exception("operations.analysis_failed")
        raise HTTPException(500, str(exc))


@app.post("/strategy/update")
async def update_strategy(strategy: dict) -> dict:
    """下发运营策略 — 通知客服更新知识库 + 直播更新话术"""
    await _event_bus.publish_event(
        event_type=EventType.STRATEGY_UPDATED,
        source="operations",
        payload=strategy,
    )
    return {"status": "published", "strategy": strategy}


@app.get("/tasks")
async def list_tasks() -> dict:
    """列出定时任务状态"""
    if _scheduler is None:
        return {"scheduler": "not_running", "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        })
    return {"scheduler": "running", "jobs": jobs}
