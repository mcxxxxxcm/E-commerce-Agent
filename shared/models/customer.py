"""客户画像模型 — 共享记忆的核心数据结构"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import UUIDMixin, Base


class CustomerProfile(UUIDMixin, Base):
    __tablename__ = "customer_profiles"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(256), index=True)

    # 画像数据
    tags: Mapped[list[str] | None] = mapped_column(JSONB, default=list)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    purchase_history: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict
    )

    # 多渠道对话摘要（共享记忆关键字段）
    conversation_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=dict,
        comment="各 Agent 写入的对话摘要，跨 Agent 共享客户上下文",
    )

    # 向量 Embedding（语义检索）
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )

    source: Mapped[str | None] = mapped_column(
        String(64), comment="来源渠道：telemarketing/live/cs"
    )
    lead_score: Mapped[int] = mapped_column(Integer, default=0, comment="意向评分 0-100")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
