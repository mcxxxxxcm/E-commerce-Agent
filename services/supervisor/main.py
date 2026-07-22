"""
Supervisor 服务入口 — FastAPI + LangGraph 编排中枢
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.config import get_settings
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger, setup_logging
from shared.tracing import init_tracing, instrument_app

from .graph import SupervisorState, build_supervisor_graph, route_to_agents
from .task_board import TaskBoard

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class TaskRequest(BaseModel):
    task_type: str
    payload: dict[str, Any] = {}
    priority: int = 5
    callback_event: str | None = None
    correlation_id: str | None = None


class TaskResponse(BaseModel):
    task_id: str
    status: str
    target_agents: list[str]
    correlation_id: str


class EventRequest(BaseModel):
    event_type: str
    source: str
    payload: dict[str, Any] = {}
    correlation_id: str | None = None


# ---------------------------------------------------------------------------
# 应用生命周期
# ---------------------------------------------------------------------------

_settings = get_settings()
_event_bus: EventBus | None = None
_supervisor_graph = None
_task_board: TaskBoard | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _supervisor_graph, _task_board

    setup_logging(service_name="supervisor", log_level=_settings.log_level)

    # EventBus
    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()

    # 注册跨 Agent 事件监听
    await _event_bus.subscribe(EventType.CUSTOMER_HIGH_INTENT, _handle_high_intent)
    await _event_bus.subscribe(EventType.CONTENT_REVIEW_NEEDED, _handle_content_review)
    await _event_bus.subscribe(EventType.STRATEGY_UPDATED, _handle_strategy_update)
    await _event_bus.subscribe(EventType.APPROVAL_GRANTED, _handle_approval_granted)

    # LangGraph 图
    _supervisor_graph = build_supervisor_graph(_event_bus)

    logger.info("supervisor.started")
    yield

    await _event_bus.disconnect()
    logger.info("supervisor.stopped")


app = FastAPI(title="Supervisor Agent", version="0.1.0", lifespan=lifespan)

# OpenTelemetry
tracer = init_tracing("supervisor", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "supervisor")

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"service": "supervisor", "status": "healthy"}


@app.post("/task", response_model=TaskResponse)
async def create_task(request: TaskRequest) -> TaskResponse:
    """创建并分发任务"""
    correlation_id = request.correlation_id or str(uuid.uuid4())

    state: SupervisorState = {
        "task_type": request.task_type,
        "payload": request.payload,
        "priority": request.priority,
        "correlation_id": correlation_id,
        "target_agents": [],
        "results": {},
        "callback_event": request.callback_event or "",
        "next_steps": [],
        "errors": [],
    }

    # 路由
    routed = route_to_agents(state)
    state["target_agents"] = routed["target_agents"]

    # 执行编排
    try:
        result = await _supervisor_graph.ainvoke(state)
    except Exception as exc:
        logger.exception("supervisor.execution_failed")
        raise HTTPException(status_code=500, detail=str(exc))

    return TaskResponse(
        task_id=correlation_id,
        status="dispatched",
        target_agents=result.get("target_agents", []),
        correlation_id=correlation_id,
    )


@app.post("/event")
async def receive_event(request: EventRequest):
    """接收外部事件并路由到对应 Agent"""
    await _event_bus.publish_event(
        event_type=request.event_type,
        source=request.source,
        payload=request.payload,
        correlation_id=request.correlation_id,
    )
    return {"status": "published", "event_type": request.event_type}


@app.get("/agents")
async def list_agents() -> dict:
    """列出所有可用 Agent 及其路由规则"""
    from .graph import TASK_ROUTING
    return {
        "agents": list(_settings.agent_urls.keys()),
        "routing": {
            k: v for k, v in TASK_ROUTING.items()
        },
    }


@app.get("/stats")
async def get_stats() -> dict:
    """获取集群任务统计"""
    return {
        "agents": list(_settings.agent_urls.keys()),
    }


# ---------------------------------------------------------------------------
# 跨 Agent 事件处理器
# ---------------------------------------------------------------------------


async def _handle_high_intent(event):
    """客服识别高意向客户 → 创建电销任务"""
    logger.info("supervisor.high_intent", customer_id=event.payload.get("customer_id"))
    await _event_bus.publish_event(
        event_type="task.telemarketing",
        source="supervisor",
        payload={
            "task_type": "purchase_lead",
            "customer_id": event.payload.get("customer_id"),
            "intent": event.payload.get("intent", ""),
        },
        correlation_id=event.correlation_id,
    )


async def _handle_content_review(event):
    """内容待审核 → 触发办公 Agent 的审批流程"""
    await _event_bus.publish_event(
        event_type="task.office",
        source="supervisor",
        payload={
            "task_type": "content_approval",
            "content_id": event.payload.get("content_id"),
        },
        correlation_id=event.correlation_id,
    )


async def _handle_strategy_update(event):
    """运营策略变更 → 更新客服知识库 + 话术库"""
    await _event_bus.publish_event(
        event_type=EventType.KNOWLEDGE_UPDATED,
        source="supervisor",
        payload=event.payload,
    )
    await _event_bus.publish_event(
        event_type=EventType.SCRIPT_UPDATED,
        source="supervisor",
        payload=event.payload,
    )


async def _handle_approval_granted(event):
    """审批通过 → 触发后续工作流"""
    approval_type = event.payload.get("approval_type", "")
    if approval_type == "promotion":
        # 大促活动审批通过 → 全链路启动
        await _event_bus.publish_event(
            event_type=EventType.PROMOTION_STARTED,
            source="supervisor",
            payload=event.payload,
        )
