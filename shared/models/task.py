"""任务/事件模型"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import UUIDMixin, Base

import enum


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLED = "cancelled"


class TaskPriority(int, enum.Enum):
    LOW = 0
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


class Task(UUIDMixin, Base):
    __tablename__ = "tasks"

    task_type: Mapped[str] = mapped_column(
        String(64), index=True, comment="任务类型"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(TaskPriority), default=TaskPriority.NORMAL
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(64), index=True, comment="目标 Agent 标识"
    )
    parent_task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    callback_event: Mapped[str | None] = mapped_column(
        String(128), comment="完成后触发的事件"
    )

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class EventLog(UUIDMixin, Base):
    __tablename__ = "event_log"

    event_type: Mapped[str] = mapped_column(String(128), index=True)
    source_agent: Mapped[str | None] = mapped_column(String(64), index=True)
    target_agent: Mapped[str | None] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(
        String(64), index=True, comment="关联 ID，串联事件链"
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, index=True
    )


class Script(UUIDMixin, Base):
    __tablename__ = "scripts"

    agent_type: Mapped[str] = mapped_column(
        String(64), index=True, comment="关联的 Agent 类型"
    )
    scenario: Mapped[str] = mapped_column(String(128), comment="适用场景")
    content: Mapped[str] = mapped_column(Text, comment="话术内容")
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Approval(UUIDMixin, Base):
    __tablename__ = "approvals"

    approval_type: Mapped[str] = mapped_column(String(64), index=True)
    requester: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True,
        comment="pending/approved/rejected"
    )
    approver: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ContentAsset(UUIDMixin, Base):
    __tablename__ = "contents"

    platform: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(
        String(32), default="article", comment="article/video/feed"
    )
    status: Mapped[str] = mapped_column(
        String(32), default="draft", index=True,
        comment="draft/pending_review/approved/published/rejected"
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="发布后效果数据"
    )

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class KnowledgeEntry(UUIDMixin, Base):
    __tablename__ = "knowledge_entries"

    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(128), index=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        "embedding", Vector(1536), nullable=True
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, default=dict
    )
    active: Mapped[bool] = mapped_column(default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
