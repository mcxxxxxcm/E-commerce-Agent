"""
AI直播 Agent 服务入口
架构: 高频短响应 — 每条弹幕/评论独立处理，话术库热更新
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

logger = get_logger(__name__)

_settings = get_settings()
_event_bus: EventBus | None = None
_llm = None

# 直播话术库 — 支持热更新
_scripts: dict[str, str] = {}
_persona: str = ""
_product_context: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _llm, _scripts, _persona, _product_context

    setup_logging(service_name="live", log_level=_settings.log_level)

    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()

    # 监听话术更新事件
    @_event_bus.on(EventType.SCRIPT_UPDATED)
    async def on_script_update(event):
        global _scripts
        _scripts = event.payload.get("scripts", {})
        logger.info("live.scripts_updated", count=len(_scripts))

    # 监听策略变更
    @_event_bus.on(EventType.STRATEGY_UPDATED)
    async def on_strategy_update(event):
        global _persona, _product_context
        _persona = event.payload.get("persona", _persona)
        _product_context = event.payload.get("product_context", _product_context)
        logger.info("live.strategy_updated")

    await _event_bus.start()

    _llm = ChatAnthropic(
        model=_settings.fast_model,  # 直播用快速模型，降低延迟
        api_key=_settings.anthropic_api_key,
        temperature=0.5,
        max_tokens=256,  # 限制输出长度，直播回复要短
    )

    # 默认话术
    _scripts = {
        "greeting": "欢迎 {username} 进入直播间！",
        "product_intro": "这款{product_name}真的超好用，{feature}，现在下单还有限时优惠哦～",
        "price_response": "价格真的已经很优惠了，今天下单还送{trial_offer}哦",
        "trust_response": "我们家做了{num_years}年了，品质有保障，支持7天无理由退换",
    }
    _persona = "亲切邻家小姐姐风格"
    _product_context = "日用百货，超高性价比"

    logger.info("live.started")
    yield
    await _event_bus.disconnect()
    logger.info("live.stopped")


app = FastAPI(title="Live Agent", version="0.1.0", lifespan=lifespan)
tracer = init_tracing("live", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "live")


class CommentRequest(BaseModel):
    username: str
    comment: str
    product_name: str = ""


class CommentResponse(BaseModel):
    reply: str
    intent: str


# 意图分类 prompt
INTENT_PROMPT = """将直播评论分类为以下类型之一：
- product_inquiry: 产品相关问题
- price: 价格相关问题
- casual: 闲聊互动
- purchase: 购买意向引导
- complaint: 投诉/不满

用户评论: {comment}

只输出类型名。"""


@app.get("/health")
async def health() -> dict:
    return {"service": "live", "status": "healthy"}


@app.post("/comment", response_model=CommentResponse)
async def handle_comment(request: CommentRequest) -> CommentResponse:
    """
    处理一条直播评论。

    高频调用 — 每条评论独立处理，不依赖历史上下文。
    """
    # 意图分类
    intent_resp = await _llm.ainvoke([
        {"role": "system", "content": INTENT_PROMPT.format(comment=request.comment)},
    ])
    intent = intent_resp.content.strip().lower()

    # 根据意图生成回复
    reply_prompt = f"""你是直播间主播，人设：{_persona}。
产品信息：{_product_context}。
用户 {request.username} 评论：{request.comment}
评论意图：{intent}

生成一条简短、有感染力的自然回复（15-40字）：
- 产品咨询 → 热情介绍卖点
- 价格询问 → 强调性价比
- 闲聊互动 → 亲切回应
- 购买意向 → 引导下单
- 投诉不满 → 安抚+私信处理
"""

    response = await _llm.ainvoke([
        {"role": "system", "content": reply_prompt},
    ])

    reply = response.content.strip()
    logger.debug("live.comment_handled", username=request.username, intent=intent)

    return CommentResponse(reply=reply, intent=intent)


@app.post("/scripts/load")
async def load_scripts(scripts: dict[str, str]) -> dict:
    """动态加载话术（热更新）"""
    global _scripts
    _scripts.update(scripts)

    # 通知内容更新（可选，方便追踪）
    await _event_bus.publish_event(
        event_type=EventType.SCRIPT_UPDATED,
        source="live",
        payload={"scripts": _scripts},
    )

    return {"status": "loaded", "count": len(_scripts)}


@app.post("/persona")
async def set_persona(persona: str, product_context: str = "") -> dict:
    """设置直播人设和产品上下文"""
    global _persona, _product_context
    _persona = persona
    _product_context = product_context or _product_context
    return {"persona": _persona, "product_context": _product_context}


@app.get("/scripts")
async def get_scripts() -> dict:
    return {"scripts": _scripts, "persona": _persona, "product_context": _product_context}
