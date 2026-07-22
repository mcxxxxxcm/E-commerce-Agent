"""
客服升级逻辑 — 高意向客户 / 复杂问题升级到电销
"""
from __future__ import annotations

from shared.eventbus import EventBus, EventType
from shared.logging import get_logger

logger = get_logger(__name__)

# 升级触发条件
ESCALATION_THRESHOLD = {
    "intent_score": 70,       # 意向评分 ≥ 70
    "high_value_keywords": [  # 高价值关键词
        "批发", "大量采购", "代理", "企业", "定制", "长期合作",
    ],
    "complexity_keywords": [  # 复杂问题（需人工）
        "怎么付款", "合同", "发票", "对公", "账期",
    ],
}


async def check_escalation(
    message: str,
    customer_id: str,
    intent_score: int = 0,
    event_bus: EventBus | None = None,
) -> bool:
    """
    检查是否需要升级到电销。

    返回 True 表示已触发升级。
    """
    should_escalate = False
    reason = ""

    # 条件1：高意向评分
    if intent_score >= ESCALATION_THRESHOLD["intent_score"]:
        should_escalate = True
        reason = f"intent_score={intent_score}"

    # 条件2：高价值关键词
    if any(kw in message for kw in ESCALATION_THRESHOLD["high_value_keywords"]):
        should_escalate = True
        reason = "high_value_keywords"

    # 条件3：复杂问题
    if any(kw in message for kw in ESCALATION_THRESHOLD["complexity_keywords"]):
        should_escalate = True
        reason = "complex_question"

    if should_escalate and event_bus:
        await event_bus.publish_event(
            event_type=EventType.CUSTOMER_HIGH_INTENT,
            source="customer_service",
            payload={
                "customer_id": customer_id,
                "reason": reason,
                "message_snippet": message[:200],
                "intent_score": intent_score,
            },
        )
        logger.info("escalation.triggered", customer_id=customer_id, reason=reason)

    return should_escalate
