"""淘宝平台适配器"""
from shared.logging import get_logger

logger = get_logger(__name__)


class TaobaoAdapter:
    """淘宝内容发布适配器"""

    async def publish(self, title: str, body: str, content_type: str = "article") -> dict:
        logger.info("taobao.publish", title=title[:50], content_type=content_type)
        return {
            "published": True,
            "platform": "taobao",
            "external_id": f"tb_mock_{hash(title) % 100000}",
            "url": f"https://www.taobao.com/item/mock",
        }
