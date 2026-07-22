"""
Supervisor 编排图 — 基于 LangGraph 的中心协调器
负责：任务路由、Agent 分发、事件驱动编排、跨 Agent 工作流
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from shared.eventbus import EventBus, Event, EventType
from shared.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class SupervisorState(TypedDict):
    """Supervisor 状态 — 贯穿整个编排流程"""

    # 核心信息
    task_type: str               # 任务类型
    payload: dict[str, Any]      # 任务负载
    priority: int                # 优先级 0-10
    correlation_id: str          # 关联 ID，串联事件链

    # Agent 路由
    target_agents: list[str]     # 目标 Agent 列表
    results: dict[str, Any]      # 各 Agent 返回结果

    # 事件
    callback_event: str          # 完成后触发的事件类型
    next_steps: list[str]        # 后续步骤（链式编排）

    # 错误
    errors: list[str]


# ---------------------------------------------------------------------------
# 路由逻辑
# ---------------------------------------------------------------------------

# 任务类型 → Agent 路由表
TASK_ROUTING: dict[str, list[str]] = {
    "customer_inquiry": ["customer_service"],
    "order_issue": ["customer_service"],
    "complaint": ["customer_service"],
    "purchase_lead": ["telemarketing"],
    "live_comment": ["live"],
    "content_generation": ["content"],
    "content_publish": ["content"],
    "daily_report": ["operations"],
    "weekly_analysis": ["operations"],
    "pricing_strategy": ["operations"],
    "competitor_analysis": ["operations"],
    "leave_approval": ["office"],
    "expense_approval": ["office"],
    "meeting_arrange": ["office"],
    "document_generate": ["office"],
    # 复合任务（跨 Agent 编排）
    "promotion_campaign": ["operations", "content", "customer_service"],
    "high_intent_lead": ["customer_service", "telemarketing"],
    "content_to_live": ["content", "live"],
    "product_display_generation": ["product_display"],
    "product_to_content": ["product_display", "content"],
}


def route_to_agents(state: SupervisorState) -> dict:
    """根据 task_type 路由到目标 Agent"""
    task_type = state["task_type"]
    agents = TASK_ROUTING.get(task_type, ["customer_service"])
    return {"target_agents": agents}


# ---------------------------------------------------------------------------
# 分发节点
# ---------------------------------------------------------------------------


async def dispatch_task(state: SupervisorState, event_bus: EventBus) -> dict:
    """
    向目标 Agent 分发任务。

    简单任务：直接发布到目标 Agent 的 Stream
    复合任务：按顺序编排，每个 Agent 完成后触发下一个
    """
    task_type = state["task_type"]
    target_agents = state["target_agents"]
    payload = state["payload"]
    correlation_id = state["correlation_id"]

    results = {}

    for agent in target_agents:
        event_type = f"task.{agent}"

        try:
            result = await event_bus.publish_and_wait(
                Event(
                    event_type=event_type,
                    source="supervisor",
                    target=agent,
                    payload={
                        "task_type": task_type,
                        **payload,
                    },
                    correlation_id=correlation_id,
                ),
                timeout=60.0,
            )
            results[agent] = result
            logger.info(
                "supervisor.task_dispatched",
                task_type=task_type,
                agent=agent,
            )

        except Exception as exc:
            logger.error(
                "supervisor.dispatch_failed",
                task_type=task_type,
                agent=agent,
                error=str(exc),
            )
            results[agent] = {"status": "failed", "error": str(exc)}

    # 检查是否有后续步骤
    return {
        "results": results,
        "next_steps": _get_next_events(task_type, results),
    }


def _get_next_events(task_type: str, results: dict) -> list[str]:
    """根据任务类型和结果，决定后续触发的事件"""
    next_events = []

    # 客服识别高意向 → 触发电销
    if task_type == "customer_inquiry":
        cs_result = results.get("customer_service", {})
        if cs_result.get("intent_score", 0) >= 70:
            next_events.append(EventType.CUSTOMER_HIGH_INTENT)

    # 内容审核通过 → 发布
    if task_type == "content_generation":
        content_result = results.get("content", {})
        if content_result.get("status") == "ready_to_publish":
            next_events.append(EventType.CONTENT_REVIEW_NEEDED)

    return next_events


# ---------------------------------------------------------------------------
# 回调处理
# ---------------------------------------------------------------------------


async def handle_callback(state: SupervisorState, event_bus: EventBus) -> dict:
    """处理 Agent 完成后的事件回调，触发后续步骤"""
    next_events = state.get("next_steps", [])

    for event_type in next_events:
        await event_bus.publish_event(
            event_type=event_type,
            source="supervisor",
            payload={
                "original_task": state["task_type"],
                "results": state["results"],
            },
            correlation_id=state["correlation_id"],
        )
        logger.info("supervisor.callback_triggered", event_type=event_type)

    return state


# ---------------------------------------------------------------------------
# 构建图
# ---------------------------------------------------------------------------


def build_supervisor_graph(event_bus: EventBus) -> StateGraph:
    """
    构建 Supervisor 编排图。

    图结构:
        route → dispatch → handle_callback → END
    """
    workflow = StateGraph(SupervisorState)

    # 节点
    workflow.add_node("route", route_to_agents)
    workflow.add_node("dispatch", lambda s: dispatch_task(s, event_bus))
    workflow.add_node("handle_callback", lambda s: handle_callback(s, event_bus))

    # 边
    workflow.set_entry_point("route")
    workflow.add_edge("route", "dispatch")
    workflow.add_conditional_edges(
        "dispatch",
        lambda s: "continue" if s.get("next_steps") else "end",
        {"continue": "handle_callback", "end": END},
    )
    workflow.add_edge("handle_callback", END)

    return workflow.compile()
