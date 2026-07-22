"""运营工具 — 销售数据查询"""
from __future__ import annotations

from shared.logging import get_logger
from shared.tools.registry import register

logger = get_logger(__name__)


@register(name="query_sales_data", tags=["analytics"], description="查询销售数据")
async def query_sales_data(period: str = "today", metric: str = "all") -> dict:
    """
    查询销售数据。period: today / yesterday / this_week / this_month
    metric: all / revenue / orders / conversion
    """
    # 生产环境替换为实际数据仓库查询
    return {
        "period": period,
        "revenue": 0.0,
        "orders": 0,
        "conversion_rate": 0.0,
        "avg_order_value": 0.0,
        "top_products": [],
        "trend": "stable",
    }


@register(name="query_product_performance", tags=["analytics", "product"], description="查询单品销售表现")
async def query_product_performance(product_id: str = "", days: int = 7) -> dict:
    """查询单品在指定天数内的销售表现"""
    return {
        "product_id": product_id,
        "days": days,
        "sales": 0,
        "views": 0,
        "conversion_rate": 0.0,
        "reviews_avg": 0.0,
    }
