"""订单咨询处理器"""
from __future__ import annotations

from shared.logging import get_logger
from shared.tools.registry import get_tool

logger = get_logger(__name__)

query_order = get_tool("query_order")
query_logistics = get_tool("query_logistics")


async def handle_order_inquiry(message: str, customer_id: str, llm, memory) -> str:
    """处理订单查询类咨询"""
    # 查询客户订单
    orders = await query_order(customer_id=customer_id)
    if not orders.get("orders"):
        return "您好，我暂未查到您的订单记录。请提供订单号以便我为您查询。"

    # 涉及物流的查询
    if any(kw in message for kw in ["物流", "到哪", "快递", "发货"]):
        latest_order = orders["orders"][0]
        logistics = await query_logistics(order_id=latest_order["order_id"])
        return await _format_logistics_response(latest_order, logistics, llm)

    # 一般订单咨询 → LLM 生成回复
    response = await llm.ainvoke([
        {"role": "system", "content": "你是电商客服，根据订单信息回答用户问题。语气亲切专业。"},
        {"role": "user", "content": f"用户问题：{message}\n\n订单信息：{orders}"},
    ])

    # 更新共享记忆
    await memory.update_summary(customer_id, "cs", {
        "last_intent": "order_inquiry",
        "last_summary": response.content[:200],
    })

    return response.content


async def _format_logistics_response(order: dict, logistics: dict, llm) -> str:
    response = await llm.ainvoke([
        {"role": "system", "content": "根据物流信息生成简洁回复。"},
        {"role": "user", "content": f"订单：{order}\n物流：{logistics}"},
    ])
    return response.content
