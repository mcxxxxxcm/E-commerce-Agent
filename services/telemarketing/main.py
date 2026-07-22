"""
AI数字人电销 Agent 服务入口
架构: LangGraph 对话状态机 + ASR/TTS 适配 + HITL 接管
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from shared.config import get_settings
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger, setup_logging
from shared.tracing import init_tracing, instrument_app

from .graph import CallState, build_telemarketing_graph

logger = get_logger(__name__)

_settings = get_settings()
_event_bus: EventBus | None = None
_llm = None
_call_graph = None

# 话术库（生产环境从数据库/Redis 加载并支持热更新）
DEFAULT_SCRIPTS = {
    "greeting": "您好，我是XX商城的专属客户顾问，看到您之前对我们的产品感兴趣，方便聊几句吗？",
    "objections": {
        "price": "我完全理解您对价格的考虑。不过咱们这款产品能帮您解决...",
        "no_need": "没关系，方便了解一下您目前在使用什么方案吗？",
        "think_again": "好的，正好我们这周有个限时优惠活动...",
    },
}

DEFAULT_PRODUCT_INFO = {
    "name": "示例商品",
    "price": "¥299",
    "features": ["高品质", "30天退换", "全国包邮"],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _llm, _call_graph

    setup_logging(service_name="telemarketing", log_level=_settings.log_level)

    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()
    await _event_bus.start()

    # 监听高意向事件——客服升级过来的线索
    @_event_bus.on(EventType.CUSTOMER_HIGH_INTENT)
    async def on_high_intent(event):
        logger.info("telemarketing.lead_received", customer_id=event.payload.get("customer_id"))

    _llm = ChatAnthropic(
        model=_settings.default_model,
        api_key=_settings.anthropic_api_key,
        temperature=0.4,
    )
    _call_graph = build_telemarketing_graph(_llm, DEFAULT_SCRIPTS, DEFAULT_PRODUCT_INFO)

    logger.info("telemarketing.started")
    yield
    await _event_bus.disconnect()
    logger.info("telemarketing.stopped")


app = FastAPI(title="Telemarketing Agent", version="0.1.0", lifespan=lifespan)
tracer = init_tracing("telemarketing", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "telemarketing")


class CallStartRequest(BaseModel):
    call_id: str = ""
    customer_id: str
    customer_name: str = ""
    initial_message: str = ""


class CallTurnRequest(BaseModel):
    call_id: str
    user_input: str


class CallResponse(BaseModel):
    call_id: str
    bot_response: str
    current_stage: str
    outcome: str | None = None
    needs_human: bool = False
    lead_score: int = 0


@app.get("/health")
async def health() -> dict:
    return {"service": "telemarketing", "status": "healthy"}


@app.post("/call/start", response_model=CallResponse)
async def start_call(request: CallStartRequest) -> CallResponse:
    """开始一通外呼"""
    import uuid

    call_id = request.call_id or str(uuid.uuid4())
    state: CallState = {
        "call_id": call_id,
        "customer_id": request.customer_id,
        "customer_name": request.customer_name,
        "current_stage": "",
        "user_input": request.initial_message,
        "bot_response": "",
        "conversation_history": [],
        "intent": "",
        "lead_score": 0,
        "outcome": "",
        "needs_human": False,
        "summary": "",
    }

    result = await _call_graph.ainvoke(state)

    return CallResponse(
        call_id=call_id,
        bot_response=result.get("bot_response", ""),
        current_stage=result.get("current_stage", ""),
        outcome=result.get("outcome"),
        needs_human=result.get("needs_human", False),
        lead_score=result.get("lead_score", 0),
    )


@app.post("/call/turn", response_model=CallResponse)
async def call_turn(request: CallTurnRequest) -> CallResponse:
    """通话中的一轮对话 — 用户说话后调用"""
    state: CallState = {
        "call_id": request.call_id,
        "customer_id": "",
        "customer_name": "",
        "current_stage": "",
        "user_input": request.user_input,
        "bot_response": "",
        "conversation_history": [],
        "intent": "",
        "lead_score": 0,
        "outcome": "",
        "needs_human": False,
        "summary": "",
    }

    result = await _call_graph.ainvoke(state)

    return CallResponse(
        call_id=request.call_id,
        bot_response=result.get("bot_response", ""),
        current_stage=result.get("current_stage", ""),
        outcome=result.get("outcome"),
        needs_human=result.get("needs_human", False),
        lead_score=result.get("lead_score", 0),
    )


@app.get("/scripts")
async def get_scripts() -> dict:
    """获取当前话术库"""
    return {"scripts": DEFAULT_SCRIPTS}


@app.post("/scripts/reload")
async def reload_scripts() -> dict:
    """热更新话术库 — 从数据库重新加载"""
    # 生产环境：从 PostgreSQL scripts 表加载
    logger.info("telemarketing.scripts_reloaded")
    return {"status": "reloaded", "count": len(DEFAULT_SCRIPTS)}
