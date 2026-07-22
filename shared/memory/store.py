"""
共享记忆 — LangGraph Store 的 PostgreSQL 持久化实现
跨 Agent 共享客户画像、对话上下文
"""
from __future__ import annotations

import json
from typing import Any

from langgraph.store.base import BaseStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger

logger = get_logger(__name__)


class SharedMemoryStore:
    """
    共享记忆存储 — 基于 PostgreSQL。

    每个 Agent 可以读写客户画像的 conversation_summary 字段，
    实现跨渠道的客户上下文共享。

    使用方式:
        store = SharedMemoryStore(session)
        profile = await store.get_profile(customer_id="C123")
        await store.update_summary(customer_id="C123", agent="cs", summary={...})
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    # ---- 客户画像 ----

    async def get_profile(self, customer_id: str | None = None, phone: str | None = None) -> dict | None:
        """获取客户画像"""
        if customer_id:
            result = await self._session.execute(
                text("SELECT * FROM customer_profiles WHERE id = :id"),
                {"id": customer_id},
            )
        elif phone:
            result = await self._session.execute(
                text("SELECT * FROM customer_profiles WHERE phone = :phone"),
                {"phone": phone},
            )
        else:
            return None

        row = result.fetchone()
        if row is None:
            return None
        return dict(row._mapping)

    async def upsert_profile(self, data: dict[str, Any]) -> str:
        """创建或更新客户画像"""
        result = await self._session.execute(
            text("""
                INSERT INTO customer_profiles (name, phone, email, tags, preferences, conversation_summary, source)
                VALUES (:name, :phone, :email, :tags::jsonb, :preferences::jsonb, :summary::jsonb, :source)
                ON CONFLICT (phone) DO UPDATE SET
                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    tags = EXCLUDED.tags,
                    preferences = EXCLUDED.preferences,
                    conversation_summary = EXCLUDED.conversation_summary,
                    updated_at = NOW()
                RETURNING id
            """),
            {
                "name": data.get("name", ""),
                "phone": data.get("phone"),
                "email": data.get("email"),
                "tags": json.dumps(data.get("tags", [])),
                "preferences": json.dumps(data.get("preferences", {})),
                "summary": json.dumps(data.get("conversation_summary", {})),
                "source": data.get("source", ""),
            },
        )
        await self._session.commit()
        row_id = result.scalar_one()
        return str(row_id)

    # ---- 跨 Agent 摘要 ----

    async def update_summary(
        self,
        customer_id: str,
        agent: str,
        summary: dict[str, Any],
    ) -> None:
        """
        更新某个 Agent 在客户画像中的对话摘要。

        各 Agent 只写自己的 key，不会互相覆盖。
        例如: {"cs": {...}, "telemarketing": {...}, "live": {...}}
        """
        current = await self.get_profile(customer_id=customer_id)
        if current is None:
            return

        existing_summary = current.get("conversation_summary", {}) or {}
        existing_summary[agent] = {
            **existing_summary.get(agent, {}),
            **summary,
            "updated_at": str(json.dumps({})),  # will be replaced
        }

        # 使用 jsonb_set 原子更新
        await self._session.execute(
            text("""
                UPDATE customer_profiles
                SET conversation_summary = :summary::jsonb,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {
                "id": customer_id,
                "summary": json.dumps(existing_summary, ensure_ascii=False),
            },
        )
        await self._session.commit()
        logger.debug("memory.summary_updated", customer_id=customer_id, agent=agent)

    async def get_shared_context(self, customer_id: str) -> str:
        """获取客户的跨 Agent 共享上下文，格式化为字符串供 LLM 使用"""
        profile = await self.get_profile(customer_id=customer_id)
        if profile is None:
            return "新客户，无历史记录。"

        parts = []
        parts.append(f"客户: {profile.get('name', '未知')}")
        parts.append(f"标签: {', '.join(profile.get('tags', []))}")
        parts.append(f"意向评分: {profile.get('lead_score', 0)}")

        summary = profile.get("conversation_summary", {}) or {}
        for agent_name, agent_summary in summary.items():
            parts.append(f"\n[{agent_name} Agent 历史]:")
            for k, v in agent_summary.items():
                parts.append(f"  {k}: {v}")

        return "\n".join(parts)
