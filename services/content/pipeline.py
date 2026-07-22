"""
内容 Pipeline — 基于 LangGraph 的选题→生成→审核→发布流程
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from shared.logging import get_logger

logger = get_logger(__name__)


class ContentState(TypedDict):
    """内容 Pipeline 状态"""

    # 输入
    topic: str                      # 选题
    platform: str                   # 目标平台
    content_type: str               # article/video_script/feed
    product_context: str            # 商品上下文

    # 生成
    outline: str                    # 大纲
    draft: str                      # 草稿
    media_urls: list[str]           # 配图/视频链接

    # 审核
    review_status: str              # pending/approved/rejected
    review_comment: str

    # 发布
    publish_status: str             # draft/published/failed
    external_url: str

    # 追踪
    metrics: dict[str, Any]


# ---------------------------------------------------------------------------
# Pipeline 节点
# ---------------------------------------------------------------------------


async def plan_topic(state: ContentState, llm) -> dict:
    """选题规划 — 根据平台和商品生成内容大纲"""
    prompt = f"""你是一个{state['platform']}平台的电商内容策划师。
商品信息：{state['product_context']}
选题方向：{state['topic']}
内容类型：{state['content_type']}

请生成内容大纲，包括：标题备选(3个)、核心卖点、结构框架。"""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    logger.info("content.topic_planned", topic=state["topic"])
    return {"outline": response.content}


async def generate_content(state: ContentState, llm) -> dict:
    """文案生成 — 根据大纲生成完整内容"""
    prompt = f"""根据以下大纲生成完整的{state['content_type']}内容：

大纲：
{state['outline']}

要求：
- 符合{state['platform']}平台的风格和调性
- 包含引人注目的开头和明确的 CTA (行动号召)
- 内容长度适中，段落清晰
- SEO 友好"""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    logger.info("content.generated", platform=state["platform"])
    return {"draft": response.content}


async def adapt_for_platform(state: ContentState, llm) -> dict:
    """平台适配 — 根据不同平台特性调整内容格式"""
    adaptations = state.get("adaptations", {})

    platform = state["platform"]
    platform_prompt = {
        "douyin": "适配为抖音短视频脚本，15-30秒，口语化，加话题标签",
        "xiaohongshu": "适配为小红书图文笔记风格，添加emoji，分点清晰，适合种草",
        "taobao": "适配为淘宝详情页文案，突出卖点、参数、优惠",
    }

    prompt = f"""将以下内容{platform_prompt.get(platform, '进行适配')}：

原始内容：
{state['draft']}"""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    adaptations[platform] = response.content
    return {"adaptations": adaptations}


async def human_review(state: ContentState) -> dict:
    """
    HITL 人工审核节点。

    流程在此暂停，等待人工审核。审核通过后才继续发布。
    """
    # LangGraph interrupt：暂停执行，等待外部确认
    approval = interrupt({
        "message": "请审核以下内容并决定是否发布",
        "platform": state["platform"],
        "title": state.get("topic", ""),
        "draft": state["draft"],
        "actions": ["approve", "reject", "revise"],
    })

    if approval.get("action") == "approve":
        return {"review_status": "approved", "review_comment": approval.get("comment", "")}
    elif approval.get("action") == "reject":
        return {"review_status": "rejected", "review_comment": approval.get("comment", "")}
    else:
        # revise: 返回修改建议，回到生成节点
        return {
            "review_status": "pending",
            "review_comment": approval.get("comment", ""),
        }


async def publish(state: ContentState, platform_adapter) -> dict:
    """发布到目标平台"""
    if state.get("review_status") != "approved":
        return {"publish_status": "skipped"}

    try:
        content = state.get("adaptations", {}).get(state["platform"], state["draft"])
        result = await platform_adapter.publish(
            title=state.get("topic", ""),
            body=content,
            content_type=state.get("content_type", "article"),
        )

        logger.info("content.published", platform=state["platform"])
        return {
            "publish_status": "published",
            "external_url": result.get("url", ""),
        }

    except Exception as exc:
        logger.error("content.publish_failed", error=str(exc))
        return {"publish_status": "failed"}


async def track_metrics(state: ContentState, db_session) -> dict:
    """效果追踪 — 记录发布后的数据"""
    return {
        "metrics": {
            "published_at": "tracked",
            "platform": state["platform"],
        }
    }


# ---------------------------------------------------------------------------
# 构建 Pipeline 图
# ---------------------------------------------------------------------------


def build_content_pipeline(llm, platform_adapter, db_session) -> StateGraph:
    """
    构建内容 Pipeline 图。

    图结构:
        plan → generate → adapt → review → [road]:
                                          ├─ approved → publish → track → END
                                          ├─ rejected → END
                                          └─ revise → generate (回环)
    """
    workflow = StateGraph(ContentState)

    workflow.add_node("plan", lambda s: plan_topic(s, llm))
    workflow.add_node("generate", lambda s: generate_content(s, llm))
    workflow.add_node("adapt", lambda s: adapt_for_platform(s, llm))
    workflow.add_node("review", human_review)
    workflow.add_node("publish", lambda s: publish(s, platform_adapter))
    workflow.add_node("track", lambda s: track_metrics(s, db_session))

    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "generate")
    workflow.add_edge("generate", "adapt")
    workflow.add_edge("adapt", "review")

    # 审核分支
    workflow.add_conditional_edges(
        "review",
        lambda s: s["review_status"],
        {
            "approved": "publish",
            "rejected": END,
            "pending": "generate",
        },
    )

    workflow.add_edge("publish", "track")
    workflow.add_edge("track", END)

    return workflow.compile()
