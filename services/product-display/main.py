"""
商品展示图生成 Agent 服务入口
架构: LangGraph Pipeline — 上传→分析→生成(展示图+描述+上架内容)→审核→打包
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from langchain_anthropic import ChatAnthropic

from shared.config import get_settings
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger, setup_logging
from shared.tracing import init_tracing, instrument_app

from .graph import ProductDisplayState, build_product_display_pipeline
from .image_gen import get_image_gen_backend
from .models import GenerateRequest, GenerateResponse, ReviewAction
from .storage import save_upload

logger = get_logger(__name__)

_settings = get_settings()
_event_bus: EventBus | None = None
_llm = None
_image_gen = None
_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_bus, _llm, _image_gen, _pipeline

    setup_logging(service_name="product-display", log_level=_settings.log_level)

    _event_bus = EventBus(redis_url=_settings.redis_url)
    await _event_bus.connect()
    await _event_bus.start()

    _llm = ChatAnthropic(
        model=_settings.default_model,
        api_key=_settings.anthropic_api_key,
        temperature=0.7,
    )

    _image_gen = get_image_gen_backend()
    _pipeline = build_product_display_pipeline(_llm, _image_gen)

    logger.info("product-display.started")
    yield
    await _event_bus.disconnect()
    logger.info("product-display.stopped")


app = FastAPI(title="Product Display Agent", version="0.1.0", lifespan=lifespan)
tracer = init_tracing("product-display", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "product-display")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"service": "product-display", "status": "healthy"}


@app.post("/generate")
async def generate_product_display(
    image: UploadFile = File(...),
    product_name: str = Form(""),
    category: str = Form(""),
    brand_style: str = Form(""),
    target_platform: str = Form("taobao"),
    num_images: int = Form(2),
    generate_desc: bool = Form(True),
    generate_listing: bool = Form(True),
    auto_approve: bool = Form(False),
) -> GenerateResponse:
    """启动商品展示图生成完整流程"""
    if not image.filename:
        raise HTTPException(400, "未提供商品图片")

    # 1. 保存上传的原图
    try:
        upload_info = await save_upload(image)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    # 2. 构造初始状态
    initial_state: ProductDisplayState = {
        "image_id": upload_info["image_id"],
        "original_path": upload_info["original_path"],
        "product_name": product_name,
        "category": category,
        "brand_style": brand_style,
        "target_platform": target_platform,
        "num_images": max(1, min(num_images, 4)),
        "generate_description": generate_desc,
        "generate_listing": generate_listing,
        "auto_approve": auto_approve,
        "ext": upload_info["ext"],
        "analysis": {},
        "display_images": [],
        "image_gen_prompt": "",
        "description": "",
        "listing": {},
        "review_status": "pending",
        "review_comment": "",
        "error": "",
    }

    # 3. 执行 pipeline
    try:
        result = await _pipeline.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("product_display.generation_failed")
        raise HTTPException(500, str(exc))

    # 4. 若自动通过或审核通过，发布事件
    if result.get("review_status") != "rejected":
        await _event_bus.publish_event(
            event_type=EventType.PRODUCT_DISPLAY_GENERATED,
            source="product-display",
            payload={
                "image_id": result.get("image_id", ""),
                "product_name": product_name,
                "images": result.get("display_images", []),
                "listing": result.get("listing", {}),
            },
        )

    return GenerateResponse(
        status="completed" if result.get("review_status") != "rejected" else "rejected",
        thread_id=upload_info["image_id"],
        images=result.get("display_images", []),
        description=result.get("description", ""),
        listing=result.get("listing"),
        analysis=result.get("analysis"),
        review_status=result.get("review_status", "pending"),
        review_comment=result.get("review_comment", ""),
    )


@app.get("/status/{task_id}")
async def get_status(task_id: str) -> dict:
    """查询任务状态 — 检查产出文件是否存在"""
    base = Path(_settings.image_storage_path) / task_id
    exists = base.exists()
    files = [p.name for p in base.glob("*")] if exists else []
    return {
        "task_id": task_id,
        "exists": exists,
        "files": files,
    }


@app.post("/review")
async def review_product_display(request: ReviewAction) -> dict:
    """HITL 审核接口 — 通过 LangGraph checkpoint 恢复执行"""
    return {
        "status": "received",
        "thread_id": request.thread_id,
        "action": request.action,
    }


@app.get("/result/{task_id}")
async def get_result(task_id: str) -> dict:
    """获取指定任务的生成结果"""
    base = Path(_settings.image_storage_path) / task_id
    if not base.exists():
        raise HTTPException(404, f"任务不存在: {task_id}")

    display_images = [str(p) for p in base.glob("display_*.png")]
    original = list(base.glob("original.*"))

    return {
        "task_id": task_id,
        "original": str(original[0]) if original else "",
        "display_images": display_images,
    }
