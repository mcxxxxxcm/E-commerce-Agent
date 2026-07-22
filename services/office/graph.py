"""
自动化办公工作流引擎 — 基于 LangGraph 的多分支审批流
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from shared.logging import get_logger

logger = get_logger(__name__)


class OfficeState(TypedDict):
    """办公工作流状态"""

    # 请求信息
    workflow_type: str             # leave / expense / meeting / document
    requester: str                 # 申请人
    payload: dict[str, Any]        # 请求负载

    # 处理
    intent: str                    # 子意图
    validated: bool                # 校验结果
    validation_errors: list[str]   # 校验错误

    # 审批
    approval_chain: list[str]      # 审批链 [主管, 经理, HR]
    current_approver: str
    approval_result: str           # approved / rejected / pending
    approval_comment: str

    # 结果
    status: str                    # success / failed / cancelled
    notification_sent: bool


# ---------------------------------------------------------------------------
# 工作流节点
# ---------------------------------------------------------------------------


async def classify_intent(state: OfficeState, llm) -> dict:
    """意图识别 — 判断具体子类型"""
    prompt = f"""根据用户输入判断办公请求的子类型：
- leave: 请假
- expense: 报销
- meeting: 会议安排
- document: 文档生成

用户输入：{state['payload'].get('message', '')}

只输出类型名。"""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    intent = response.content.strip().lower()

    # 确定审批链
    approval_chains = {
        "leave": ["manager", "hr"],
        "expense": ["manager", "finance"],
        "meeting": [],
        "document": ["manager"],
    }

    return {
        "intent": intent,
        "approval_chain": approval_chains.get(intent, ["manager"]),
    }


async def validate(state: OfficeState) -> dict:
    """数据校验节点"""
    intent = state["intent"]
    payload = state["payload"]
    errors = []

    if intent == "leave":
        if not payload.get("start_date"):
            errors.append("缺少开始日期")
        if not payload.get("end_date"):
            errors.append("缺少结束日期")

    elif intent == "expense":
        if not payload.get("amount"):
            errors.append("缺少报销金额")
        if not payload.get("category"):
            errors.append("缺少报销类别")

    elif intent == "meeting":
        if not payload.get("title"):
            errors.append("缺少会议标题")

    return {"validated": len(errors) == 0, "validation_errors": errors}


async def approval_chain(state: OfficeState) -> dict:
    """
    多级审批链 — 通过 LangGraph interrupt 实现 HITL

    每级审批暂停，等待对应审批人确认。
    """
    for approver in state["approval_chain"]:
        result = interrupt({
            "type": "approval",
            "approver": approver,
            "workflow_type": state["workflow_type"],
            "requester": state["requester"],
            "payload": state["payload"],
            "message": f"请 {approver} 审批 {state['requester']} 的 {state['workflow_type']} 请求",
        })

        if result.get("action") == "reject":
            return {
                "current_approver": approver,
                "approval_result": "rejected",
                "approval_comment": result.get("comment", ""),
            }

    return {
        "current_approver": state["approval_chain"][-1],
        "approval_result": "approved",
        "approval_comment": "全部审批通过",
    }


async def execute(state: OfficeState, oa_adapter) -> dict:
    """
    执行节点 — 审批通过后执行实际操作
    """
    intent = state["intent"]

    try:
        if intent == "leave":
            await oa_adapter.submit_leave(state["requester"], state["payload"])
        elif intent == "expense":
            await oa_adapter.submit_expense(state["requester"], state["payload"])
        elif intent == "meeting":
            await oa_adapter.create_meeting(state["requester"], state["payload"])
        elif intent == "document":
            await oa_adapter.generate_document(state["requester"], state["payload"])

        return {"status": "success"}
    except Exception as exc:
        logger.error("office.execute_failed", intent=intent, error=str(exc))
        return {"status": "failed"}


async def notify(state: OfficeState, notifier, event_bus) -> dict:
    """通知节点 — 发送审批结果通知"""
    message = (
        f"您的 {state['workflow_type']} 申请已 {state['approval_result']}。"
        f"{state.get('approval_comment', '')}"
    )

    await notifier.send(state["requester"], message)

    # 大促审批通过 → 通知 Supervisor
    if state["workflow_type"] == "promotion" and state["approval_result"] == "approved":
        await event_bus.publish_event(
            event_type="approval.granted",
            source="office",
            payload={
                "approval_type": "promotion",
                "requester": state["requester"],
                "payload": state["payload"],
            },
        )

    return {"notification_sent": True}


# ---------------------------------------------------------------------------
# 构建图
# ---------------------------------------------------------------------------


def build_office_graph(llm, oa_adapter, notifier, event_bus) -> StateGraph:
    """
    构建办公工作流图。

    图结构:
        classify → validate → [road]:
                              ├─ valid → approval_chain → [road]:
                              │                              ├─ approved → execute → notify → END
                              │                              └─ rejected → notify → END
                              └─ invalid → END
    """
    workflow = StateGraph(OfficeState)

    workflow.add_node("classify", lambda s: classify_intent(s, llm))
    workflow.add_node("validate", validate)
    workflow.add_node("approval_chain", approval_chain)
    workflow.add_node("execute", lambda s: execute(s, oa_adapter))
    workflow.add_node("notify", lambda s: notify(s, notifier, event_bus))

    workflow.set_entry_point("classify")
    workflow.add_edge("classify", "validate")

    workflow.add_conditional_edges(
        "validate",
        lambda s: "valid" if s["validated"] else "invalid",
        {"valid": "approval_chain", "invalid": END},
    )

    workflow.add_conditional_edges(
        "approval_chain",
        lambda s: s["approval_result"],
        {"approved": "execute", "rejected": "notify"},
    )

    workflow.add_edge("execute", "notify")
    workflow.add_edge("notify", END)

    return workflow.compile()
