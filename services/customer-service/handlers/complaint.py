"""投诉处理 + 热点升级"""
from __future__ import annotations

from shared.eventbus import EventType
from shared.logging import get_logger
from shared.tools.registry import get_tool

logger = get_logger(__name__)

query_order = get_tool("query_order")
send_notification = get_tool("send_notification")


async def handle_complaint(message: str, customer_id: str, llm, memory, event_bus) -> str:
    """处理投诉 — 严重投诉自动升级到运营"""
    orders = await query_order(customer_id=customer_id)

    # LLM 分析投诉严重程度
    severity_check = await llm.ainvoke([
        {
            "role": "system",
            "content": (
                "分析投诉严重程度，输出 JSON："
                '{"severity": "low|medium|high|crisis", "category": "...", "summary": "..."}'
            ),
        },
        {"role": "user", "content": f"投诉内容：{message}"},
    ])

    severity = _parse_severity(severity_check.content)

    # 高严重度 → 升级到运营 + 通知
    if severity in ("high", "crisis"):
        await event_bus.publish_event(
            event_type=EventType.CUSTOMER_COMPLAINT,
            source="customer_service",
            payload={
                "customer_id": customer_id,
                "severity": severity,
                "message": message,
            },
        )
        await send_notification(
            channel="feishu",
            recipient="ops_team",
            message=f"[{severity.upper()}级投诉] 客户 {customer_id}: {message[:200]}",
        )
        logger.warning("complaint.escalated", customer_id=customer_id, severity=severity)

    # 生成安抚回复
    response = await llm.ainvoke([
        {
            "role": "system",
            "content": (
                "你是电商客服，正在处理客户投诉。态度诚恳，先道歉，再给出解决方案。"
                f"投诉严重级别：{severity}。"
            ),
        },
        {"role": "user", "content": f"投诉内容：{message}\n订单信息：{orders}"},
    ])

    await memory.update_summary(customer_id, "cs", {
        "last_intent": "complaint",
        "severity": severity,
        "last_summary": response.content[:200],
    })

    return response.content


def _parse_severity(llm_output: str) -> str:
    """从 LLM 输出中提取严重程度"""
    import json
    try:
        data = json.loads(llm_output)
        return data.get("severity", "medium")
    except json.JSONDecodeError:
        if "crisis" in llm_output.lower():
            return "crisis"
        if "high" in llm_output.lower():
            return "high"
        return "medium"
