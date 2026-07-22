"""
OA 系统适配器 — 统一抽象飞书/钉钉/企业微信等 OA 平台
"""
from __future__ import annotations

from typing import Any

import httpx

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()


class OAAdapter:
    """
    OA 系统抽象层。

    生产环境替换为对应的 OA SDK / API 调用：
    - 飞书开放平台: https://open.feishu.cn/
    - 钉钉开放平台: https://open.dingtalk.com/
    """

    async def submit_leave(self, requester: str, payload: dict[str, Any]) -> dict:
        """提交请假申请"""
        logger.info("oa.leave_submitted", requester=requester)
        return {"status": "submitted", "workflow": "leave"}

    async def submit_expense(self, requester: str, payload: dict[str, Any]) -> dict:
        """提交报销申请"""
        logger.info("oa.expense_submitted", requester=requester)
        return {"status": "submitted", "workflow": "expense"}

    async def create_meeting(self, requester: str, payload: dict[str, Any]) -> dict:
        """创建会议"""
        logger.info("oa.meeting_created", requester=requester)
        return {"status": "created", "workflow": "meeting"}

    async def generate_document(self, requester: str, payload: dict[str, Any]) -> dict:
        """生成文档"""
        logger.info("oa.document_generated", requester=requester)
        return {"status": "generated", "workflow": "document"}


class Notifier:
    """通知服务"""

    async def send(self, recipient: str, message: str) -> None:
        """发送通知消息"""
        logger.info("notify.sent", recipient=recipient, message=message[:100])

        # 飞书通知
        if _settings.feishu_webhook_url:
            async with httpx.AsyncClient() as client:
                await client.post(
                    _settings.feishu_webhook_url,
                    json={"msg_type": "text", "content": {"text": f"收件人: {recipient}\n{message}"}},
                    timeout=10,
                )
