"""
商品展示图生成 Pipeline — 基于 LangGraph 的 分析→生成→审核→打包 流程

图结构:
    upload → analyze ──┬── generate_image ──────┬── review ── package_output → END
                        ├── generate_description ──┤            │ (rejected)
                        └── generate_listing ──────┘       END  ←┘
                                                              │ (revise)
                                                    generate_description
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Annotated, Any, Literal

from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from shared.logging import get_logger

from .image_gen import download_generated_image, get_image_gen_backend
from .prompts import (
    IMAGE_ANALYSIS_SYSTEM,
    LISTING_SYSTEM,
    build_analysis_prompt,
    build_description_prompt,
    build_image_gen_prompt,
    build_listing_prompt,
)
from .storage import save_generated_image

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class ProductDisplayState(TypedDict):
    """商品展示图生成 Pipeline 状态"""

    # 输入
    image_id: str
    original_path: str
    product_name: str
    category: str
    brand_style: str
    target_platform: str
    num_images: int
    generate_description: bool
    generate_listing: bool
    auto_approve: bool
    ext: str

    # 分析结果
    analysis: dict[str, Any]

    # 生成结果
    display_images: list[str]
    image_gen_prompt: str
    description: str
    listing: dict[str, Any]

    # 审核
    review_status: str
    review_comment: str

    # 错误
    error: str


# ---------------------------------------------------------------------------
# Pipeline 节点
# ---------------------------------------------------------------------------


async def upload_image(state: ProductDisplayState) -> dict:
    """上传节点 — 确认图片已存储，记录信息"""
    logger.info("product_display.uploaded", image_id=state["image_id"])
    return {}


async def analyze_image(state: ProductDisplayState, llm) -> dict:
    """
    图像分析节点 — 使用 Vision Model 分析商品原图。
    输出结构化的商品特征分析。
    """
    prompt = build_analysis_prompt(state.get("product_name", ""), state.get("category", ""))

    # 读取图片文件用于 vision 分析
    from pathlib import Path

    image_path = Path(state["original_path"])
    if not image_path.exists():
        return {"error": f"原图文件不存在: {state['original_path']}"}

    ext = state.get("ext", ".jpg").lstrip(".")
    mime_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    messages = [
        {"role": "system", "content": IMAGE_ANALYSIS_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_data}"},
                },
            ],
        },
    ]

    try:
        response = await llm.ainvoke(messages)
        # 尝试解析 JSON 响应
        content = response.content.strip()
        # 处理可能的 markdown 代码块
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        analysis = json.loads(content)
        logger.info("product_display.analysis_done", category=analysis.get("category", ""))
        return {"analysis": analysis, "error": ""}
    except json.JSONDecodeError:
        # 如果 LLM 没返回严格 JSON，把原始文本保存为分析结果
        logger.warning("product_display.analysis_json_parse_failed")
        return {
            "analysis": {"raw": response.content, "category": state.get("category", ""), "style": "", "features": []},
            "error": "",
        }
    except Exception as exc:
        logger.exception("product_display.analysis_failed")
        return {"error": str(exc)}


async def generate_display_image(state: ProductDisplayState, image_gen) -> dict:
    """
    展示图生成节点 — 基于分析结果调用图像生成 API。
    生成电商风格的商品展示图。
    """
    analysis = state.get("analysis", {})
    if not analysis:
        return {"display_images": [], "image_gen_prompt": ""}

    prompt = build_image_gen_prompt(analysis, state.get("product_name", ""))

    try:
        results = await image_gen.generate(prompt, num_images=state.get("num_images", 2))
    except Exception as exc:
        logger.exception("product_display.image_gen_failed")
        return {"display_images": [], "image_gen_prompt": prompt, "error": str(exc)}

    image_urls: list[str] = []
    for i, result in enumerate(results):
        url = result.get("url", "")
        b64 = result.get("b64_json")

        if b64:
            # Base64 数据直接保存
            image_data = base64.b64decode(b64)
            saved_path = await save_generated_image(state["image_id"], image_data, i)
            image_urls.append(saved_path)
            logger.info("product_display.image_saved_from_b64", path=saved_path)
        elif url:
            # 下载并保存
            try:
                image_data = await download_generated_image(url)
                saved_path = await save_generated_image(state["image_id"], image_data, i)
                image_urls.append(saved_path)
                logger.info("product_display.image_saved_from_url", path=saved_path)
            except Exception as exc:
                logger.error("product_display.download_failed", url=url, error=str(exc))
                image_urls.append(url)  # 兜底：直接用 URL

    return {"display_images": image_urls, "image_gen_prompt": prompt}


async def generate_description(state: ProductDisplayState, llm) -> dict:
    """商品描述生成节点 — 基于分析结果生成营销文案"""
    analysis = state.get("analysis", {})
    if not analysis:
        return {"description": ""}

    prompt = build_description_prompt(
        analysis,
        state.get("product_name", ""),
        state.get("brand_style", ""),
    )

    messages = [
        {"role": "system", "content": "你是一个资深的电商文案策划师。请用中文输出。"},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await llm.ainvoke(messages)
        logger.info("product_display.description_generated")
        return {"description": response.content}
    except Exception as exc:
        logger.exception("product_display.description_failed")
        return {"description": "", "error": str(exc)}


async def generate_listing_content(state: ProductDisplayState, llm) -> dict:
    """上架内容生成节点 — 生成结构化的上架关键信息"""
    analysis = state.get("analysis", {})
    if not analysis:
        return {"listing": {}}

    prompt = build_listing_prompt(
        analysis,
        state.get("description", ""),
        state.get("product_name", ""),
        state.get("target_platform", "taobao"),
    )

    messages = [
        {"role": "system", "content": LISTING_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        listing = json.loads(content)
        logger.info("product_display.listing_generated")
        return {"listing": listing}
    except json.JSONDecodeError:
        logger.warning("product_display.listing_json_parse_failed")
        return {"listing": {"raw": response.content}}
    except Exception as exc:
        logger.exception("product_display.listing_failed")
        return {"listing": {}, "error": str(exc)}


async def review_human(state: ProductDisplayState) -> dict:
    """
    HITL 人工审核节点。
    流程在此暂停等待人工审核。审核通过后才继续打包输出。
    """
    if state.get("auto_approve"):
        return {"review_status": "approved", "review_comment": ""}

    approval = interrupt({
        "message": "请审核商品展示图及文案",
        "image_id": state.get("image_id", ""),
        "product_name": state.get("product_name", ""),
        "images": state.get("display_images", []),
        "description": state.get("description", ""),
        "listing": state.get("listing", {}),
        "actions": ["approve", "reject", "revise"],
    })

    action = approval.get("action", "reject")
    return {
        "review_status": action if action != "revise" else "pending",
        "review_comment": approval.get("comment", ""),
    }


async def package_output(state: ProductDisplayState) -> dict:
    """打包输出节点 — 将所有结果组装为最终输出"""
    logger.info(
        "product_display.packaged",
        image_id=state["image_id"],
        image_count=len(state.get("display_images", [])),
    )
    return {}


# ---------------------------------------------------------------------------
# 构建 Pipeline 图
# ---------------------------------------------------------------------------


def build_product_display_pipeline(
    llm,
    image_gen,
) -> StateGraph:
    """
    构建商品展示图生成 Pipeline。

    图结构:
        upload → analyze ──┬── generate_image ──────┬── review ── package_output → END
                            ├── generate_description ──┤
                            └── generate_listing ──────┘
    分析后三个生成节点并行执行，最后汇集到审核节点。
    """
    workflow = StateGraph(ProductDisplayState)

    # 添加节点
    workflow.add_node("upload", upload_image)
    workflow.add_node("analyze", lambda s: analyze_image(s, llm))
    workflow.add_node("generate_image", lambda s: generate_display_image(s, image_gen))
    workflow.add_node("generate_description", lambda s: generate_description(s, llm))
    workflow.add_node("generate_listing", lambda s: generate_listing_content(s, llm))
    workflow.add_node("review", review_human)
    workflow.add_node("package", package_output)

    # 设置入口
    workflow.set_entry_point("upload")

    # upload → analyze
    workflow.add_edge("upload", "analyze")

    # analyze → 三路并行生成
    workflow.add_edge("analyze", "generate_image")
    workflow.add_edge("analyze", "generate_description")
    workflow.add_edge("analyze", "generate_listing")

    # 三路汇集到 review
    workflow.add_edge("generate_image", "review")
    workflow.add_edge("generate_description", "review")
    workflow.add_edge("generate_listing", "review")

    # review 分支
    workflow.add_conditional_edges(
        "review",
        lambda s: s["review_status"],
        {
            "approved": "package",
            "rejected": END,
            "pending": "generate_description",  # revise: 回到描述生成
        },
    )

    workflow.add_edge("package", END)

    return workflow.compile()
