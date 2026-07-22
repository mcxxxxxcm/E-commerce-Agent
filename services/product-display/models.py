"""
商品展示图生成模块 — Pydantic 模型定义
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """商品展示图生成请求"""
    product_name: str = Field(default="", description="商品名称（可选）")
    category: str = Field(default="", description="品类提示（可选）")
    brand_style: str = Field(default="", description="品牌调性")
    target_platform: str = Field(default="taobao", description="目标平台: taobao/douyin/xiaohongshu")
    num_images: int = Field(default=2, ge=1, le=4, description="生成图片数量")
    generate_description: bool = Field(default=True, description="是否生成商品描述")
    generate_listing: bool = Field(default=True, description="是否生成上架内容")
    auto_approve: bool = Field(default=False, description="跳过人工审核")


class ReviewAction(BaseModel):
    """人工审核操作"""
    thread_id: str = Field(..., description="任务线程ID")
    action: Literal["approve", "reject", "revise"] = Field(..., description="审核动作")
    comment: str = Field(default="", description="审核意见")


class StatusRequest(BaseModel):
    """任务状态查询"""
    task_id: str = Field(..., description="任务ID")


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class ImageAnalysisResult(BaseModel):
    """图像分析结果"""
    category: str = ""
    material: str = ""
    color_palette: list[str] = Field(default_factory=list)
    style: str = ""
    features: list[str] = Field(default_factory=list)
    use_scenario: str = ""
    mood: str = ""


class DisplayImageResult(BaseModel):
    """展示图生成结果"""
    image_urls: list[str] = Field(default_factory=list)
    prompt_used: str = ""


class ListingContent(BaseModel):
    """上架关键内容"""
    title: str = ""
    short_title: str = ""
    selling_points: list[str] = Field(default_factory=list)
    bullet_features: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    suggested_price_range: str = ""
    target_audience: str = ""


class GenerateResponse(BaseModel):
    """生成流程响应"""
    status: str  # processing / completed / rejected
    thread_id: str = ""
    images: list[str] = Field(default_factory=list)
    description: str = ""
    listing: ListingContent | None = None
    analysis: ImageAnalysisResult | None = None
    review_status: str = "pending"
    review_comment: str = ""
    error: str = ""
