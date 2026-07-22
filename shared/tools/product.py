"""商品工具 — 商品信息查询"""
from __future__ import annotations

from shared.tools.registry import register


@register(name="query_product", tags=["product"], description="查询商品详情，包括价格、库存、规格")
async def query_product(product_id: str = "", keyword: str = "") -> dict:
    """
    查询商品信息。提供 product_id 精确查询，或 keyword 模糊搜索。

    返回: {"products": [{"id", "name", "price", "stock", "specs", "description"}]}
    """
    return {"products": [], "total_count": 0}


@register(name="check_stock", tags=["product"], description="检查商品库存")
async def check_stock(product_id: str) -> dict:
    return {"product_id": product_id, "in_stock": False, "quantity": 0}
