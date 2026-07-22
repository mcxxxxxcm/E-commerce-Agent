"""
自动化办公 Agent 服务入口
架构: LangGraph 工作流引擎 + 多级审批 HITL
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from shared.config import get_settings
from shared.eventbus import EventBus
from shared.logging import get_logger, setup_logging
from shared.tracing import init_tracing, instrument_app

from .graph import OfficeState, build_office_graph
from .oa_adapter import Notifier, OAAdapter

logger = get_logger(__name__)

_settings = get_settings()
_event_bus: EventBus | None = None
_llm = None
_workflow = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _llm, _workflow

    setup_logging(service_name="office", log_level=_settings.log_level)

    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()
    await _event_bus.start()

    _llm = ChatAnthropic(
        model=_settings.fast_model,
        api_key=_settings.anthropic_api_key,
        temperature=0.1,
    )

    _workflow = build_office_graph(_llm, OAAdapter(), Notifier(), _event_bus)

    logger.info("office.started")
    yield
    await _event_bus.disconnect()
    logger.info("office.stopped")


app = FastAPI(title="Office Agent", version="0.1.0", lifespan=lifespan)
tracer = init_tracing("office", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "office")


class WorkflowRequest(BaseModel):
    workflow_type: str
    requester: str
    payload: dict[str, Any] = {}


class ApprovalAction(BaseModel):
    thread_id: str
    action: str  # approve / reject
    comment: str = ""


@app.get("/health")
async def health() -> dict:
    return {"service": "office", "status": "healthy"}


@app.post("/workflow/start")
async def start_workflow(request: WorkflowRequest) -> dict:
    """启动办公工作流"""
    state: OfficeState = {
        "workflow_type": request.workflow_type,
        "requester": request.requester,
        "payload": request.payload,
        "intent": "",
        "validated": False,
        "validation_errors": [],
        "approval_chain": [],
        "current_approver": "",
        "approval_result": "pending",
        "approval_comment": "",
        "status": "",
        "notification_sent": False,
    }

    try:
        result = await _workflow.ainvoke(state)
    except Exception as exc:
        logger.exception("office.workflow_failed")
        raise HTTPException(500, str(exc))

    return {
        "status": result.get("status", "completed"),
        "intent": result.get("intent"),
        "approval_result": result.get("approval_result"),
        "validation_errors": result.get("validation_errors", []),
    }


@app.post("/approval")
async def submit_approval(request: ApprovalAction) -> dict:
    """提交审批意见 — 恢复 HITL interrupt"""
    return {"status": "received", "thread_id": request.thread_id, "action": request.action}


@app.get("/workflows")
async def list_workflows() -> dict:
    """列出支持的办公工作流"""
    return {
        "workflows": [
            {"type": "leave", "description": "请假审批", "approvers": ["manager", "hr"]},
            {"type": "expense", "description": "报销审批", "approvers": ["manager", "finance"]},
            {"type": "meeting", "description": "会议安排", "approvers": []},
            {"type": "document", "description": "文档生成", "approvers": ["manager"]},
        ]
    }
