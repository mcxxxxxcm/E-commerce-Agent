"""
AI文案生成+发布 Agent 服务入口
架构: LangGraph Pipeline — 选题→生成→HITL审核→发布→追踪
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from shared.config import get_settings
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger, setup_logging
from shared.tracing import init_tracing, instrument_app

from .pipeline import ContentState, build_content_pipeline
from .platforms import PLATFORM_ADAPTERS

logger = get_logger(__name__)

_settings = get_settings()
_event_bus: EventBus | None = None
_llm = None
_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _llm, _pipeline, _platform_adapter

    setup_logging(service_name="content", log_level=_settings.log_level)

    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()
    await _event_bus.start()

    _llm = ChatAnthropic(
        model=_settings.default_model,
        api_key=_settings.anthropic_api_key,
        temperature=0.7,
    )

    # 默认使用抖音适配器（实际使用时按需选择）
    _platform_adapter = PLATFORM_ADAPTERS["douyin"]()
    _pipeline = build_content_pipeline(_llm, _platform_adapter, None)

    logger.info("content.started")
    yield
    await _event_bus.disconnect()
    logger.info("content.stopped")


app = FastAPI(title="Content Agent", version="0.1.0", lifespan=lifespan)
tracer = init_tracing("content", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "content")

_platform_adapter = None


class ContentRequest(BaseModel):
    topic: str
    platform: str = "douyin"
    content_type: str = "article"
    product_context: str = ""
    auto_publish: bool = False


class ReviewAction(BaseModel):
    thread_id: str
    action: str  # approve / reject / revise
    comment: str = ""


@app.get("/health")
async def health() -> dict:
    return {"service": "content", "status": "healthy"}


@app.post("/generate")
async def generate_content(request: ContentRequest) -> dict:
    """启动内容生成流程"""
    adapter_cls = PLATFORM_ADAPTERS.get(request.platform)
    if adapter_cls is None:
        raise HTTPException(400, f"不支持的平台: {request.platform}")

    platform_adapter = adapter_cls()
    pipeline = build_content_pipeline(_llm, platform_adapter, None)

    initial_state: ContentState = {
        "topic": request.topic,
        "platform": request.platform,
        "content_type": request.content_type,
        "product_context": request.product_context,
        "outline": "",
        "draft": "",
        "media_urls": [],
        "review_status": "pending",
        "review_comment": "",
        "publish_status": "draft",
        "external_url": "",
        "metrics": {},
    }

    try:
        result = await pipeline.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("content.generation_failed")
        raise HTTPException(500, str(exc))

    # 如果未设置 HITL 或自动发布
    if request.auto_publish and result.get("review_status") != "rejected":
        # 发布事件 → 通知直播 Agent 有新脚本可用
        await _event_bus.publish_event(
            event_type=EventType.SCRIPT_GENERATED,
            source="content",
            payload={
                "topic": request.topic,
                "platform": request.platform,
                "external_url": result.get("external_url", ""),
            },
        )

    return {
        "status": "success",
        "platform": request.platform,
        "draft": result.get("draft", ""),
        "outline": result.get("outline", ""),
        "review_status": result.get("review_status", "pending"),
    }


@app.post("/review")
async def review_content(request: ReviewAction) -> dict:
    """HITL 审核接口 — 人工审核后调用"""
    # 通过 LangGraph interrupt 机制恢复执行
    # 实际生产环境需要配合 checkpoint 实现
    return {"status": "received", "thread_id": request.thread_id, "action": request.action}


@app.post("/publish")
async def direct_publish(platform: str, title: str, body: str, content_type: str = "article") -> dict:
    """直接发布内容（跳过生成和审核流程）"""
    adapter_cls = PLATFORM_ADAPTERS.get(platform)
    if adapter_cls is None:
        raise HTTPException(400, f"不支持的平台: {platform}")

    adapter = adapter_cls()
    result = await adapter.publish(title=title, body=body, content_type=content_type)
    return result
