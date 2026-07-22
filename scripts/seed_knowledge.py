"""
知识库种子数据 — 初始化 FAQ、商品知识、话术脚本
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from shared.config import get_settings
from shared.logging import setup_logging, get_logger
from shared.knowledge import KnowledgeRetriever

logger = get_logger(__name__)

# 初始 FAQ 数据
FAQ_DATA = [
    {
        "title": "如何查询订单物流信息？",
        "content": "用户可以在「我的订单」中找到对应订单，点击「查看物流」即可查看实时物流信息。快递单号和物流公司也会显示在订单详情中。",
        "category": "faq",
    },
    {
        "title": "退货退款流程是什么？",
        "content": "1. 在订单详情中点击「申请售后」; 2. 选择退货/退款原因并提交; 3. 等待审核（通常1-2小时）；4. 审核通过后按照指引寄回商品；5. 仓库签收后1-3个工作日退款到原账户。",
        "category": "faq",
    },
    {
        "title": "商品支持多久无理由退货？",
        "content": "我们支持7天无理由退货。自签收之日起7天内，商品未使用、包装完好、不影响二次销售，即可申请退货退款。部分特殊商品（如定制类、生鲜类）除外。",
        "category": "faq",
    },
    {
        "title": "如何修改订单地址？",
        "content": "订单未发货前可以修改地址：进入订单详情 → 点击「修改地址」→ 输入新地址并保存。如果订单已发货，需要联系客服协助拦截或转寄。",
        "category": "faq",
    },
    {
        "title": "投诉和意见反馈渠道",
        "content": "用户可以通过以下渠道进行投诉或反馈: 1. 在线客服（7x24小时）; 2. 客服热线 400-XXX-XXXX; 3. 订单详情中的「投诉/建议」入口。所有投诉会在24小时内响应处理。",
        "category": "faq",
    },
    {
        "title": "优惠券使用规则",
        "content": "优惠券在结算时自动抵扣。每笔订单限用一张优惠券，不能与其他优惠叠加使用（平台通用券除外）。优惠券有使用期限，过期自动作废。",
        "category": "faq",
    },
]


async def seed_knowledge_base():
    setup_logging(service_name="seed-kb")

    settings = get_settings()
    db_url = settings.database_url_sync or (
        f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(db_url)
    session = Session(engine)

    try:
        retriever = KnowledgeRetriever(session)

        for item in FAQ_DATA:
            entry_id = await retriever.add_knowledge(
                title=item["title"],
                content=item["content"],
                category=item["category"],
            )
            logger.info("knowledge.seeded", id=entry_id, title=item["title"][:40])

        logger.info("seed_kb.complete", count=len(FAQ_DATA))
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_knowledge_base())
