"""抖音平台适配器"""
from shared.logging import get_logger

logger = get_logger(__name__)


class DouyinAdapter:
    """抖音内容发布适配器"""

    async def publish(self, title: str, body: str, content_type: str = "article") -> dict:
        """
        发布内容到抖音。

        生产环境需接入抖音开放平台 API：
        - 视频上传: /video/upload/
        - 内容发布: /video/publish/
        """
        logger.info("douyin.publish", title=title[:50], content_type=content_type)
        return {
            "published": True,
            "platform": "douyin",
            "external_id": f"dy_mock_{hash(title) % 100000}",
            "url": f"https://www.douyin.com/video/mock",
        }
