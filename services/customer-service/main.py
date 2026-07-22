"""
AI客服 Agent 服务入口
架构: LangGraph 意图路由 + 领域处理器 + SSE 流式输出
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from shared.config import get_settings
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger, setup_logging
from shared.memory import SharedMemoryStore
from shared.tracing import init_tracing, instrument_app

from .escalation import check_escalation
from .router import Intent, classify_intent, INTENT_HANDLERS
from .sse import stream_response

from .handlers import (
    handle_after_sale,
    handle_complaint,
    handle_order_inquiry,
    handle_product_consult,
)

logger = get_logger(__name__)

_settings = get_settings()
_event_bus: EventBus | None = None
_llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _llm

    setup_logging(service_name="customer-service", log_level=_settings.log_level)

    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()
    await _event_bus.start()

    _llm = ChatAnthropic(
        model=_settings.default_model,
        api_key=_settings.anthropic_api_key,
        temperature=0.3,
    )

    logger.info("customer-service.started")

    yield

    await _event_bus.disconnect()
    logger.info("customer-service.stopped")


app = FastAPI(title="Customer Service Agent", version="0.1.0", lifespan=lifespan)
tracer = init_tracing("customer-service", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "customer-service")


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    customer_id: str = "anonymous"
    session_id: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    reply: str
    intent: str
    escalated: bool = False
    customer_id: str


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"service": "customer-service", "status": "healthy"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    客服对话接口。

    流程: 意图分类 → 领域处理器 → 结果 → (可选)升级到电销
    """
    # 意图分类
    intent = await classify_intent(request.message, _llm)

    # 获取共享记忆上下文
    # memory = SharedMemoryStore(session) — 这里简化，从全局 session 获取

    # 路由到对应处理器
    handler_map = {
        Intent.ORDER_INQUIRY: handle_order_inquiry,
        Intent.AFTER_SALE: handle_after_sale,
        Intent.PRODUCT_CONSULT: handle_product_consult,
        Intent.COMPLAINT: handle_complaint,
        Intent.GENERAL_FAQ: _handle_faq,
        Intent.HIGH_INTENT: _handle_high_intent,
    }

    handler = handler_map.get(intent, _handle_faq)

    try:
        # 调用对应处理器（complaint 需要 event_bus，high_intent 需要升级）
        reply = await handler(request.message, request.customer_id, _llm, _DummyMemory())

        # 检查是否需要升级
        escalated = await check_escalation(
            message=request.message,
            customer_id=request.customer_id,
            event_bus=_event_bus,
        )
    except Exception as exc:
        logger.exception("cs.handler_error")
        reply = "抱歉，我遇到了一些问题，请稍后再试。"
        escalated = False

    return ChatResponse(
        reply=reply,
        intent=intent.value,
        escalated=escalated,
        customer_id=request.customer_id,
    )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """流式客服对话"""
    chat_response = await chat(request)
    return StreamingResponse(
        stream_response(chat_response.reply),
        media_type="text/event-stream",
    )


# ---- Fallback handlers ----


async def _handle_faq(message: str, customer_id: str, llm, memory) -> str:
    """FAQ 兜底处理"""
    response = await llm.ainvoke([
        {
            "role": "system",
            "content": (
                "你是电商客服助手。回答通用问题，语气亲切专业。"
                "如果问题超出范围，引导用户提供更多信息或转接人工。"
            ),
        },
        {"role": "user", "content": message},
    ])
    return response.content


async def _handle_high_intent(message: str, customer_id: str, llm, memory) -> str:
    """高意向客户处理 — 收集需求 + 触发升级"""
    response = await llm.ainvoke([
        {
            "role": "system",
            "content": (
                "你发现用户有很强的购买意向。你要："
                "1. 了解用户需求（数量、用途、时间）"
                "2. 告知会有专人联系"
                "3. 记录关键信息"
            ),
        },
        {"role": "user", "content": message},
    ])
    return response.content


class _DummyMemory:
    """开发环境使用的占位 memory"""
    async def update_summary(self, *args, **kwargs): pass
