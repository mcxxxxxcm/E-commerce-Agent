"""通知工具 — 多渠道消息发送"""
from __future__ import annotations

import httpx
from shared.config import get_settings
from shared.logging import get_logger
from shared.tools.registry import register

logger = get_logger(__name__)


@register(name="send_notification", tags=["notification"], description="发送通知消息，支持飞书、钉钉、短信等渠道")
async def send_notification(channel: str, recipient: str, message: str) -> dict:
    """
    发送通知。channel 可选: feishu, dingtalk, sms, email
    """
    settings = get_settings()

    if channel == "feishu":
        return await _send_feishu(settings.feishu_webhook_url, message)
    elif channel == "dingtalk":
        return await _send_dingtalk(settings.dingtalk_webhook_url, message)
    else:
        logger.warning("notification.channel_unsupported", channel=channel)
        return {"sent": False, "reason": f"Unsupported channel: {channel}"}


async def _send_feishu(webhook_url: str, message: str) -> dict:
    if not webhook_url:
        return {"sent": False, "reason": "Feishu webhook not configured"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            webhook_url,
            json={"msg_type": "text", "content": {"text": message}},
            timeout=10,
        )
        return {"sent": resp.is_success, "channel": "feishu"}


async def _send_dingtalk(webhook_url: str, message: str) -> dict:
    if not webhook_url:
        return {"sent": False, "reason": "DingTalk webhook not configured"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            webhook_url,
            json={"msgtype": "text", "text": {"content": message}},
            timeout=10,
        )
        return {"sent": resp.is_success, "channel": "dingtalk"}
