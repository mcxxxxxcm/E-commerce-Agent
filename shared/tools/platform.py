"""平台工具 — 多平台内容发布"""
from __future__ import annotations

from shared.logging import get_logger
from shared.tools.registry import register

logger = get_logger(__name__)


@register(name="publish_content", tags=["platform"], description="发布内容到指定平台（抖音、小红书、淘宝等）")
async def publish_content(platform: str, title: str, body: str, content_type: str = "article") -> dict:
    """
    发布内容到外部平台。
    platform: douyin, xiaohongshu, taobao
    """
    # 生产环境替换为各平台 API 调用
    logger.info("platform.publish", platform=platform, title=title[:50], content_type=content_type)
    return {
        "published": True,
        "platform": platform,
        "external_id": f"{platform}_mock_id",
        "url": f"https://{platform}.com/content/mock_id",
    }
