"""
任务看板 — 基于 PostgreSQL 的任务状态追踪系统
所有跨 Agent 任务的状态中枢
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.logging import get_logger
from shared.models import Task, TaskPriority, TaskStatus

logger = get_logger(__name__)


class TaskBoard:
    """
    任务看板。

    使用方式:
        board = TaskBoard(session)
        task_id = await board.create("customer_inquiry", {...}, priority=5)
        task = await board.get(task_id)
        await board.update_status(task_id, TaskStatus.RUNNING)
        await board.complete(task_id, result={...})
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        task_type: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        parent_task_id: str | None = None,
        callback_event: str | None = None,
    ) -> str:
        """创建任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            task_type=task_type,
            payload=payload,
            status=TaskStatus.PENDING,
            priority=priority,
            agent_id=agent_id,
            parent_task_id=parent_task_id,
            callback_event=callback_event,
        )
        self._session.add(task)
        await self._session.commit()
        logger.info("taskboard.created", task_id=task_id, task_type=task_type)
        return task_id

    async def get(self, task_id: str) -> Task | None:
        """获取任务详情"""
        result = await self._session.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        """更新任务状态"""
        await self._session.execute(
            update(Task).where(Task.id == task_id).values(status=status, updated_at=datetime.now(UTC))
        )
        await self._session.commit()

    async def complete(self, task_id: str, result: dict[str, Any] | None = None) -> None:
        """标记任务完成"""
        await self._session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                status=TaskStatus.SUCCESS,
                result=result or {},
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.commit()
        logger.info("taskboard.completed", task_id=task_id)

    async def fail(self, task_id: str, error_message: str) -> None:
        """标记任务失败"""
        await self._session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                status=TaskStatus.FAILED,
                error_message=error_message,
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.commit()
        logger.error("taskboard.failed", task_id=task_id, error=error_message)

    async def list_by_status(self, status: TaskStatus, limit: int = 50) -> list[Task]:
        """按状态列出任务"""
        result = await self._session.execute(
            select(Task)
            .where(Task.status == status)
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_agent(self, agent_id: str, limit: int = 50) -> list[Task]:
        """查询某个 Agent 的任务列表"""
        result = await self._session.execute(
            select(Task)
            .where(Task.agent_id == agent_id)
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_for_agent(self, agent_id: str) -> list[Task]:
        """获取某个 Agent 的待处理任务"""
        return await self.list_by_status(TaskStatus.PENDING)

    async def get_stats(self) -> dict[str, int]:
        """获取任务统计数据"""
        result = await self._session.execute(
            text("""
                SELECT status::text, COUNT(*) as cnt
                FROM tasks
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY status
            """)
        )
        return {row[0]: row[1] for row in result.fetchall()}
