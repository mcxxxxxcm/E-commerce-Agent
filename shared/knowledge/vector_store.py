"""
向量知识库 — 基于 pgvector 的语义检索
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

logger = get_logger(__name__)


class VectorStore:
    """
    pgvector 向量存储封装。

    使用方式:
        store = VectorStore(session, embedding_dim=1536)
        await store.add("知识标题", "知识内容", category="faq", metadata={})
        results = await store.search("用户查询", top_k=5)
    """

    def __init__(self, session: AsyncSession, embedding_dim: int = 1536):
        self._session = session
        self._dim = embedding_dim

    async def add(
        self,
        title: str,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
    ) -> str:
        """添加知识条目"""
        embedding_str = _format_vector(embedding) if embedding else "NULL"
        meta_json = _escape_json(metadata or {})

        result = await self._session.execute(
            text("""
                INSERT INTO knowledge_entries (title, content, category, metadata, embedding, active)
                VALUES (:title, :content, :category, :meta::jsonb, :embedding::vector, TRUE)
                RETURNING id
            """),
            {
                "title": title,
                "content": content,
                "category": category,
                "meta": meta_json,
                "embedding": embedding_str,
            },
        )
        await self._session.commit()
        row_id = result.scalar_one()
        logger.debug("knowledge.added", id=str(row_id), title=title[:50])
        return str(row_id)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        category: str | None = None,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """
        向量相似度搜索。

        Args:
            query_embedding: 查询向量
            top_k: 返回条数
            category: 可选类别过滤
            threshold: 相似度阈值 (余弦距离)
        """
        embedding_str = _format_vector(query_embedding)

        category_filter = "AND category = :category" if category else ""

        result = await self._session.execute(
            text(f"""
                SELECT id, title, content, category, metadata,
                       1 - (embedding <=> :embedding::vector) AS similarity
                FROM knowledge_entries
                WHERE active = TRUE
                  {category_filter}
                  AND 1 - (embedding <=> :embedding::vector) >= :threshold
                ORDER BY embedding <=> :embedding::vector
                LIMIT :top_k
            """),
            {
                "embedding": embedding_str,
                "threshold": threshold,
                "top_k": top_k,
                **({"category": category} if category else {}),
            },
        )

        rows = result.fetchall()
        return [
            {
                "id": str(row[0]),
                "title": row[1],
                "content": row[2],
                "category": row[3],
                "metadata": row[4],
                "similarity": round(float(row[5]), 4),
            }
            for row in rows
        ]

    async def delete(self, entry_id: str) -> None:
        """软删除知识条目"""
        await self._session.execute(
            text("UPDATE knowledge_entries SET active = FALSE WHERE id = :id"),
            {"id": entry_id},
        )
        await self._session.commit()

    async def count(self) -> int:
        result = await self._session.execute(
            text("SELECT COUNT(*) FROM knowledge_entries WHERE active = TRUE")
        )
        return result.scalar_one()


def _format_vector(vec: list[float] | None) -> str:
    """格式化为 pgvector 兼容的字符串"""
    if vec is None:
        return "NULL"
    return f"[{','.join(str(v) for v in vec)}]"


def _escape_json(data: dict) -> str:
    import json
    return json.dumps(data, ensure_ascii=False)
