"""
AI电销 Agent — 基于 LangGraph 的对话状态机

状态流转:
    开场白 → 意图识别 → 话术分支 → 异议处理 → 促成/标记
                            ↑              │
                            └── 循环对话 ──┘
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from shared.logging import get_logger

logger = get_logger(__name__)


class CallState(TypedDict):
    """电销通话状态"""

    # 会话
    call_id: str
    customer_id: str
    customer_name: str

    # 对话
    current_stage: str       # greeting / qualification / pitching / objection / closing
    user_input: str          # 当前轮用户输入（ASR 转写）
    bot_response: str        # 当前轮机器人回复（TTS 播报）

    # 上下文
    conversation_history: list[dict[str, str]]
    intent: str              # 识别到的用户意图
    lead_score: int          # 意向评分 0-100

    # 结果
    outcome: str             # interested / not_interested / callback / transferred / hung_up
    needs_human: bool        # 是否需要人工接管
    summary: str


# ---------------------------------------------------------------------------
# 状态节点
# ---------------------------------------------------------------------------


async def greet(state: CallState, llm, scripts: dict) -> dict:
    """开场白 — 根据客户画像选择开场话术"""
    name = state.get("customer_name", "先生/女士")
    greeting = scripts.get("greeting", f"您好{name}，我是XX商城的客户顾问，方便聊几句吗？")

    return {
        "current_stage": "greeting",
        "bot_response": greeting,
        "conversation_history": [{"role": "assistant", "content": greeting}],
    }


async def recognize_intent(state: CallState, llm) -> dict:
    """意图识别 — 分析用户回复的意图"""
    if not state.get("user_input"):
        return {"intent": "neutral", "current_stage": "qualification"}

    prompt = f"""分析以下电话对话中的客户意图，输出 JSON：
{{"intent": "interested|neutral|not_interested|objection|question", "lead_score": 0-100, "keywords": ["..."]}}

对话历史:
{state['conversation_history'][-5:]}

客户最新回复: {state['user_input']}"""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    import json
    try:
        result = json.loads(response.content)
        intent = result.get("intent", "neutral")
        lead_score = result.get("lead_score", 50)
    except json.JSONDecodeError:
        intent = "neutral"
        lead_score = 50

    # 状态转移
    if intent == "interested":
        next_stage = "pitching"
    elif intent == "objection":
        next_stage = "objection"
    elif intent == "not_interested":
        next_stage = "closing"
    else:
        next_stage = "qualification"

    return {
        "intent": intent,
        "lead_score": max(0, min(100, lead_score)),
        "current_stage": next_stage,
    }


async def qualify(state: CallState, llm, scripts: dict) -> dict:
    """
    需求挖掘 — 通过提问了解客户需求。

    使用 SPIN 销售法：Situation → Problem → Implication → Need-payoff
    """
    prompt = f"""你正在进行电话销售的需求挖掘阶段。根据对话历史，生成一个自然的问题来了解客户需求。
使用 SPIN 销售法提问。

对话历史:
{state['conversation_history']}

上轮客户回复: {state.get('user_input', '')}

生成你的下一句回复（只输出回复文本，不要输出角色标记）："""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    history = state["conversation_history"] + [
        {"role": "assistant", "content": response.content}
    ]

    return {
        "bot_response": response.content,
        "conversation_history": history,
    }


async def pitch(state: CallState, llm, scripts: dict, product_info: dict) -> dict:
    """
    产品推介 — 根据客户需求推荐对应的产品方案
    """
    prompt = f"""你正在进行电话销售的产品推介阶段。

产品信息: {product_info}
客户意向评分: {state['lead_score']}
对话历史: {state['conversation_history'][-5:]}

根据客户需求和产品特点，生成产品推介话术。重点突出与客户需求匹配的卖点。
（只输出回复文本）："""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    history = state["conversation_history"] + [
        {"role": "assistant", "content": response.content}
    ]

    return {
        "bot_response": response.content,
        "conversation_history": history,
    }


async def handle_objection(state: CallState, llm, scripts: dict) -> dict:
    """
    异议处理 — 处理客户的疑虑和拒绝

    常见异议:
    - 价格太高 → 价值重塑 / 比价
    - 不需要 → 场景激发
    - 再考虑 → 限时优惠 / 紧迫感
    - 已有供应商 → 差异化优势
    """
    objection_scripts = scripts.get("objections", {})

    prompt = f"""你正在处理电话销售中的客户异议。

客户异议: {state.get('user_input', '')}
可用话术参考: {objection_scripts}

生成处理异议的回复，先认同再转化 (Feel-Felt-Found 方法)：
（只输出回复文本）："""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    history = state["conversation_history"] + [
        {"role": "assistant", "content": response.content}
    ]

    return {
        "bot_response": response.content,
        "conversation_history": history,
    }


async def close(state: CallState, llm) -> dict:
    """
    促成/结束 — 尝试促成成交或礼貌结束通话
    """
    prompt = f"""通话即将结束。根据对话历史决定合适的结束方式：
- 如果客户有购买意向：尝试促成下一步（预约回访/发送资料/引导下单）
- 如果客户不感兴趣：礼貌结束通话，留下好印象
- 如果客户有异议未解决：再次尝试解决

对话历史: {state['conversation_history'][-5:]}
意向评分: {state['lead_score']}

生成结束话术（只输出回复文本）："""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    # 判断结果
    if state["lead_score"] >= 80:
        outcome = "interested"
        needs_human = True
    elif state["lead_score"] >= 50:
        outcome = "callback"
        needs_human = False
    elif state["lead_score"] >= 20:
        outcome = "not_interested"
        needs_human = False
    else:
        outcome = "hung_up"
        needs_human = False

    # 高意向 → HITL 人工接管
    if needs_human:
        interrupt({
            "type": "human_takeover",
            "call_id": state["call_id"],
            "customer_id": state["customer_id"],
            "lead_score": state["lead_score"],
            "summary": response.content[:200],
            "message": f"高意向客户，请人工接管。意向评分: {state['lead_score']}",
        })

    return {
        "bot_response": response.content,
        "outcome": outcome,
        "needs_human": needs_human,
        "current_stage": "closing",
        "summary": response.content[:200],
    }


# ---------------------------------------------------------------------------
# 构建图
# ---------------------------------------------------------------------------


def build_telemarketing_graph(llm, scripts: dict, product_info: dict) -> StateGraph:
    """
    构建电销对话状态机。

    图结构:
        greet → intent_loop ──→ closing → END
                  ↑    │
                  └────┘ (qualify → pitch → objection 循环)
    """
    workflow = StateGraph(CallState)

    workflow.add_node("greet", lambda s: greet(s, llm, scripts))
    workflow.add_node("recognize_intent", lambda s: recognize_intent(s, llm))
    workflow.add_node("qualify", lambda s: qualify(s, llm, scripts))
    workflow.add_node("pitch", lambda s: pitch(s, llm, scripts, product_info))
    workflow.add_node("handle_objection", lambda s: handle_objection(s, llm, scripts))
    workflow.add_node("close", lambda s: close(s, llm))

    workflow.set_entry_point("greet")
    workflow.add_edge("greet", "recognize_intent")

    # 意图 → 状态路由
    workflow.add_conditional_edges(
        "recognize_intent",
        lambda s: s["current_stage"],
        {
            "qualification": "qualify",
            "pitching": "pitch",
            "objection": "handle_objection",
            "closing": "close",
        },
    )

    # 各阶段 → 回到意图识别（循环直到 closing）
    workflow.add_edge("qualify", "recognize_intent")
    workflow.add_edge("pitch", "recognize_intent")
    workflow.add_edge("handle_objection", "recognize_intent")
    workflow.add_edge("close", END)

    return workflow.compile()
