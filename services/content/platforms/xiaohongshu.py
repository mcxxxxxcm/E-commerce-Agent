"""小红书平台适配器"""
from shared.logging import get_logger

logger = get_logger(__name__)


class XiaohongshuAdapter:
    """小红书内容发布适配器"""

    async def publish(self, title: str, body: str, content_type: str = "article") -> dict:
        logger.info("xiaohongshu.publish", title=title[:50], content_type=content_type)
        return {
            "published": True,
            "platform": "xiaohongshu",
            "external_id": f"xhs_mock_{hash(title) % 100000}",
            "url": f"https://www.xiaohongshu.com/explore/mock",
        }
