"""售后处理 — 退货/退款/换货"""
from __future__ import annotations

from shared.logging import get_logger
from shared.tools.registry import get_tool

logger = get_logger(__name__)

process_refund = get_tool("process_refund")
query_order = get_tool("query_order")


async def handle_after_sale(message: str, customer_id: str, llm, memory) -> str:
    """处理售后请求"""
    orders = await query_order(customer_id=customer_id)

    if not orders.get("orders"):
        return (
            "很抱歉给您带来不便。我暂时没有查询到您的订单，"
            "请提供订单号，我马上为您处理售后事宜。"
        )

    # LLM 分析售后原因并生成方案
    response = await llm.ainvoke([
        {
            "role": "system",
            "content": (
                "你是电商售后客服。根据用户描述和订单信息，判断售后类型（退货/退款/换货/维修），"
                "给出解决方案。注意安抚用户情绪。"
            ),
        },
        {
            "role": "user",
            "content": f"用户问题：{message}\n\n订单信息：{orders}",
        },
    ])

    await memory.update_summary(customer_id, "cs", {
        "last_intent": "after_sale",
        "last_summary": response.content[:200],
    })

    return response.content
