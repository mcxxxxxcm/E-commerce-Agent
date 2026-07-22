"""周报定时任务"""
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger

logger = get_logger(__name__)


async def weekly_analysis_task(agent, event_bus: EventBus | None = None) -> None:
    """每周一早 9:15 生成周报"""
    try:
        result = await agent.ainvoke({
            "messages": [{
                "role": "user",
                "content": (
                    "生成本周运营周报。包括："
                    "1. 本周销售数据总览（GMV、订单量、转化率、客单价）"
                    "2. 与上周对比分析"
                    "3. 各品类表现排行"
                    "4. 竞品动态分析"
                    "5. 下周运营策略建议"
                    "6. 需要重点关注的问题"
                ),
            }]
        })

        report = result.get("messages", [{}])[-1].get("content", "")

        if event_bus:
            await event_bus.publish_event(
                event_type="report.generated",
                source="operations",
                payload={"type": "weekly", "content": report[:1000]},
            )
            # 周报结果同步到客服知识库
            await event_bus.publish_event(
                event_type=EventType.STRATEGY_UPDATED,
                source="operations",
                payload={"weekly_report_summary": report[:500]},
            )

        logger.info("ops.weekly_analysis_generated")

    except Exception as exc:
        logger.error("ops.weekly_analysis_failed", error=str(exc))
