"""商品咨询处理"""
from __future__ import annotations

from shared.tools.registry import get_tool

query_product = get_tool("query_product")
check_stock = get_tool("check_stock")


async def handle_product_consult(message: str, customer_id: str, llm, memory) -> str:
    """处理商品咨询"""
    # 从消息中提取商品关键词（简化版：用最后几个词做搜索）
    # 生产环境应该使用 NER 或 LLM 提取
    response = await llm.ainvoke([
        {
            "role": "system",
            "content": "你是电商客服，回答商品相关问题。你拥有商品知识库的检索能力。",
        },
        {"role": "user", "content": message},
    ])

    await memory.update_summary(customer_id, "cs", {
        "last_intent": "product_consult",
        "last_summary": response.content[:200],
    })

    return response.content
