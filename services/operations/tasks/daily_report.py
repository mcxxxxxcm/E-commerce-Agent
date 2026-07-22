"""日报定时任务"""
from shared.eventbus import EventBus, EventType
from shared.logging import get_logger

logger = get_logger(__name__)


async def daily_report_task(agent, event_bus: EventBus | None = None) -> None:
    """每日早 9:05 生成日报"""
    try:
        result = await agent.ainvoke({
            "messages": [{
                "role": "user",
                "content": (
                    "生成今日日报。包括："
                    "1. 昨日销售数据概览（GMV、订单量、转化率）"
                    "2. Top 10 商品排行"
                    "3. 异常数据标注（与昨日对比）"
                    "4. 今日运营建议"
                ),
            }]
        })

        report = result.get("messages", [{}])[-1].get("content", "")

        # 发送通知
        if event_bus:
            await event_bus.publish_event(
                event_type="report.generated",
                source="operations",
                payload={"type": "daily", "content": report[:500]},
            )

        logger.info("ops.daily_report_generated")

    except Exception as exc:
        logger.error("ops.daily_report_failed", error=str(exc))
