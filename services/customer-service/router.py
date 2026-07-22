"""
客服意图路由 — 分类用户输入到领域处理器
"""
from __future__ import annotations

from enum import StrEnum


class Intent(StrEnum):
    ORDER_INQUIRY = "order_inquiry"
    AFTER_SALE = "after_sale"
    PRODUCT_CONSULT = "product_consult"
    COMPLAINT = "complaint"
    GENERAL_FAQ = "general_faq"
    HIGH_INTENT = "high_intent"  # 高意向（需升级到电销）


# 意图关键词映射
INTENT_KEYWORDS: dict[Intent, list[str]] = {
    Intent.ORDER_INQUIRY: ["订单", "物流", "发货", "到哪", "快递", "查单", "什么时候到"],
    Intent.AFTER_SALE: ["退货", "退款", "换货", "售后", "维修", "退换"],
    Intent.PRODUCT_CONSULT: ["规格", "尺码", "颜色", "材质", "多少钱", "价格", "优惠"],
    Intent.COMPLAINT: ["投诉", "差评", "不满", "质量差", "坏", "破损", "虚假"],
    Intent.HIGH_INTENT: ["怎么买", "下单", "批发", "大量", "代理", "合作"],
}

# 意图 → 函数名
INTENT_HANDLERS: dict[Intent, str] = {
    Intent.ORDER_INQUIRY: "handle_order_inquiry",
    Intent.AFTER_SALE: "handle_after_sale",
    Intent.PRODUCT_CONSULT: "handle_product_consult",
    Intent.COMPLAINT: "handle_complaint",
    Intent.GENERAL_FAQ: "handle_general_faq",
    Intent.HIGH_INTENT: "handle_high_intent",
}


async def classify_intent(message: str, llm) -> Intent:
    """
    基于 LLM 的意图分类。

    先关键词快速匹配，匹配不到再走 LLM。
    """
    # 快速关键词匹配
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in message for kw in keywords):
            return intent

    # LLM 兜底分类
    try:
        response = await llm.ainvoke([
            {
                "role": "system",
                "content": f"将以下用户消息分类为：{', '.join(i.value for i in Intent)}。只输出分类名。",
            },
            {"role": "user", "content": message},
        ])
        intent_str = response.content.strip().lower()
        for intent in Intent:
            if intent.value in intent_str:
                return intent
    except Exception:
        pass

    return Intent.GENERAL_FAQ
