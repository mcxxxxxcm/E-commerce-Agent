"""
CRM 工具 — 客户关系查询与操作
"""
from __future__ import annotations

from shared.tools.registry import register


@register(name="query_customer", tags=["crm"], description="查询客户信息，包括基本资料、标签、购买历史")
async def query_customer(customer_id: str = "", phone: str = "") -> dict:
    """
    查询客户信息。提供 customer_id 或 phone 其中之一即可。

    返回: {"id", "name", "phone", "email", "tags", "lead_score", "conversation_summary"}
    """
    # 生产环境替换为实际 CRM API 调用
    return {
        "id": customer_id or "unknown",
        "name": "",
        "phone": phone,
        "tags": [],
        "lead_score": 0,
        "conversation_summary": {},
    }


@register(name="update_customer_tags", tags=["crm"], description="更新客户标签")
async def update_customer_tags(customer_id: str, tags: str) -> dict:
    """更新客户标签，tags 为逗号分隔的标签列表"""
    return {"customer_id": customer_id, "tags": [t.strip() for t in tags.split(",")], "updated": True}


@register(name="update_lead_score", tags=["crm"], description="更新客户意向评分 (0-100)")
async def update_lead_score(customer_id: str, score: int) -> dict:
    return {"customer_id": customer_id, "lead_score": max(0, min(100, score)), "updated": True}
