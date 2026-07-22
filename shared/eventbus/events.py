"""
事件类型定义 — 所有 Agent 间协同事件的枚举
集中管理事件类型，保证全集群一致性
"""
from __future__ import annotations

from enum import StrEnum


class EventType(StrEnum):
    """Agent 间协同事件类型"""

    # --- 客户相关 ---
    CUSTOMER_HIGH_INTENT = "customer.high_intent"
    CUSTOMER_COMPLAINT = "customer.complaint"
    CUSTOMER_PROFILE_UPDATED = "customer.profile_updated"

    # --- 策略相关 ---
    STRATEGY_UPDATED = "strategy.updated"
    PROMOTION_STARTED = "promotion.started"
    PROMOTION_ENDED = "promotion.ended"
    PRICING_CHANGED = "pricing.changed"

    # --- 内容相关 ---
    SCRIPT_GENERATED = "script.generated"
    SCRIPT_UPDATED = "script.updated"
    CONTENT_PUBLISHED = "content.published"
    CONTENT_REVIEW_NEEDED = "content.review_needed"

    # --- 审批相关 ---
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"

    # --- 任务相关 ---
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # --- 商品展示图 ---
    PRODUCT_DISPLAY_GENERATED = "product.display_generated"
    PRODUCT_DISPLAY_REVIEW_NEEDED = "product.display_review_needed"

    # --- 知识库 ---
    KNOWLEDGE_UPDATED = "knowledge.updated"
    KNOWLEDGE_RETRIEVED = "knowledge.retrieved"
