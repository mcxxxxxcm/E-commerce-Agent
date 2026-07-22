"""订单工具 — 订单查询与操作"""
from __future__ import annotations

from shared.tools.registry import register


@register(name="query_order", tags=["order"], description="按订单号或客户ID查询订单详情")
async def query_order(order_id: str = "", customer_id: str = "") -> dict:
    """
    查询订单。提供 order_id 或 customer_id 其中之一。

    返回: {"orders": [{"order_id", "status", "items", "total", "created_at", ...}]}
    """
    return {"orders": [], "total_count": 0}


@register(name="query_logistics", tags=["order"], description="查询物流信息")
async def query_logistics(order_id: str) -> dict:
    return {"order_id": order_id, "status": "unknown", "tracking_number": "", "nodes": []}


@register(name="process_refund", tags=["order"], description="处理退款/售后申请")
async def process_refund(order_id: str, reason: str = "") -> dict:
    return {"order_id": order_id, "refund_status": "pending", "reason": reason}
