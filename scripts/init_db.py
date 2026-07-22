"""
数据库初始化脚本 — 创建所有表、索引
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from shared.config import get_settings
from shared.models import Base
from shared.logging import setup_logging, get_logger

logger = get_logger(__name__)


async def init_database():
    setup_logging(service_name="init-db")

    settings = get_settings()
    db_url = settings.database_url or (
        f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    logger.info("connecting", url=db_url.replace(settings.postgres_password, "***"))

    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        # 启用 pgvector 扩展
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))

        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)

        logger.info("database.initialized", tables=len(Base.metadata.tables))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
