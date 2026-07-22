"""
RAG 检索接口 — 面向 Agent 的统一知识检索
"""
from __future__ import annotations

from typing import Any

from langchain_openai import OpenAIEmbeddings

from shared.config import get_settings
from shared.knowledge.vector_store import VectorStore
from shared.logging import get_logger

logger = get_logger(__name__)


class KnowledgeRetriever:
    """
    知识库检索器。

    组合 Embedding 模型 + VectorStore，提供统一的 RAG 检索接口。

    使用方式:
        retriever = KnowledgeRetriever(session)
        results = await retriever.retrieve("如何退货", top_k=3)
        context = retriever.format_context(results)
    """

    def __init__(self, session, embedding_model: str | None = None):
        settings = get_settings()
        self._embedding_model = OpenAIEmbeddings(
            model=embedding_model or settings.embedding_model,
            dimensions=settings.embedding_dimension,
            api_key=settings.openai_api_key,
        )
        self._store = VectorStore(session, settings.embedding_dimension)

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """检索知识"""
        query_embedding = self._embedding_model.embed_query(query)
        return await self._store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            category=category,
            threshold=threshold,
        )

    def retrieve_sync(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """同步检索（用于 LangChain tool）"""
        import asyncio
        return asyncio.run(self.retrieve(query, top_k))

    async def add_knowledge(
        self,
        title: str,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """添加知识（自动生成 embedding）"""
        embedding = self._embedding_model.embed_documents([content])[0]
        return await self._store.add(
            title=title,
            content=content,
            category=category,
            metadata=metadata,
            embedding=embedding,
        )

    @staticmethod
    def format_context(results: list[dict]) -> str:
        """将检索结果格式化为 Agent 可用的上下文字符串"""
        if not results:
            return "未找到相关知识。"

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r['title']} (相关度: {r['similarity']})")
            lines.append(f"    {r['content'][:500]}")
            lines.append("")
        return "\n".join(lines)
