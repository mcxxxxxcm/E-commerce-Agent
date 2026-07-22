"""
统一异常定义 — 所有服务共享的异常类型和错误码
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """业务错误码"""

    # 通用
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # Agent 相关
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    AGENT_EXECUTION_FAILED = "AGENT_EXECUTION_FAILED"

    # 任务相关
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_ALREADY_EXISTS = "TASK_ALREADY_EXISTS"
    TASK_DEPENDENCY_FAILED = "TASK_DEPENDENCY_FAILED"

    # 事件相关
    EVENT_PUBLISH_FAILED = "EVENT_PUBLISH_FAILED"
    EVENT_SUBSCRIBE_FAILED = "EVENT_SUBSCRIBE_FAILED"

    # 知识库
    KNOWLEDGE_INDEX_FAILED = "KNOWLEDGE_INDEX_FAILED"
    KNOWLEDGE_RETRIEVAL_FAILED = "KNOWLEDGE_RETRIEVAL_FAILED"

    # HITL
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_TIMEOUT = "APPROVAL_TIMEOUT"


class AgentClusterError(Exception):
    """所有自定义异常的基类"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: dict | None = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class AgentNotFoundError(AgentClusterError):
    def __init__(self, agent_name: str):
        super().__init__(
            f"Agent '{agent_name}' not found",
            code=ErrorCode.AGENT_NOT_FOUND,
            details={"agent": agent_name},
        )


class AgentExecutionError(AgentClusterError):
    def __init__(self, agent_name: str, reason: str):
        super().__init__(
            f"Agent '{agent_name}' execution failed: {reason}",
            code=ErrorCode.AGENT_EXECUTION_FAILED,
            details={"agent": agent_name, "reason": reason},
        )


class TaskNotFoundError(AgentClusterError):
    def __init__(self, task_id: str):
        super().__init__(
            f"Task '{task_id}' not found",
            code=ErrorCode.TASK_NOT_FOUND,
            details={"task_id": task_id},
        )


class EventPublishError(AgentClusterError):
    def __init__(self, event_type: str, reason: str):
        super().__init__(
            f"Failed to publish event '{event_type}': {reason}",
            code=ErrorCode.EVENT_PUBLISH_FAILED,
            details={"event_type": event_type, "reason": reason},
        )


class HITLRequired(AgentClusterError):
    """需要人工审批的信号"""

    def __init__(self, task_id: str, reason: str):
        super().__init__(
            f"Human approval required for task '{task_id}': {reason}",
            code=ErrorCode.APPROVAL_REQUIRED,
            details={"task_id": task_id, "reason": reason},
        )
