"""
事件总线 — Redis Streams 实现
Agent 间异步通信基础设施，支持发布/订阅、消费者组、消息持久化

使用方式:
    from shared.eventbus import EventBus, Event

    bus = EventBus(redis_url="redis://localhost:6379/0")

    # 发布
    await bus.publish(Event(
        event_type="customer.high_intent",
        source="customer_service",
        payload={"customer_id": "C123"},
    ))

    # 订阅
    async def handle_high_intent(event: Event):
        ...

    await bus.subscribe("customer.high_intent", handle_high_intent)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis
from pydantic import BaseModel, Field

from shared.exceptions import EventPublishError
from shared.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Event 数据模型
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """事件结构"""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    source: str
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def from_message(cls, data: dict) -> "Event":
        """从 Redis Stream 消息反序列化"""
        return cls(**{k: v for k, v in data.items() if k != "_redis_id"})

    def to_message(self) -> dict[str, str]:
        """序列化为 Redis Stream 消息"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "target": self.target or "",
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "correlation_id": self.correlation_id or "",
            "timestamp": self.timestamp,
        }


EventHandler = Callable[[Event], Awaitable[None]]

# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

STREAM_PREFIX = "agent:events"
GROUP_NAME = "agent-cluster"
DEAD_LETTER_STREAM = "agent:dead_letter"


class EventBus:
    """
    Redis Streams 事件总线。

    特性:
    - 消费者组模式：同一 Agent 多实例共享消费组，消息不重复处理
    - 死信队列：处理失败的消息自动转入 dead_letter
    - 持久化：消息写入 Redis Stream，重启不丢失
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        consumer_group: str = GROUP_NAME,
        max_retries: int = 3,
    ):
        self._redis_url = redis_url
        self._consumer_group = consumer_group
        self._max_retries = max_retries
        self._redis: aioredis.Redis | None = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._listener_tasks: dict[str, asyncio.Task] = {}

    async def connect(self) -> None:
        """建立 Redis 连接"""
        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info("eventbus.connected", redis_url=self._redis_url)

    async def disconnect(self) -> None:
        """关闭连接，取消所有监听任务"""
        for task in self._listener_tasks.values():
            task.cancel()
        if self._redis:
            await self._redis.close()
            logger.info("eventbus.disconnected")

    @property
    def redis(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("EventBus not connected. Call `await bus.connect()` first.")
        return self._redis

    # ---- 发布 ----

    async def publish(self, event: Event) -> str:
        """发布事件到 Stream"""
        stream_key = f"{STREAM_PREFIX}:{event.event_type}"
        try:
            msg_id = await self.redis.xadd(
                stream_key, event.to_message(), maxlen=100_000
            )
            logger.debug(
                "eventbus.published",
                event_type=event.event_type,
                event_id=event.event_id,
                msg_id=msg_id,
            )
            return msg_id
        except Exception as exc:
            raise EventPublishError(event.event_type, str(exc)) from exc

    async def publish_and_wait(self, event: Event, timeout: float = 30.0) -> dict:
        """
        发布事件并等待响应（请求-响应模式）。
        用于需要同步结果的场景，如 Supervisor 分发任务后等待 Agent 返回。
        """
        reply_stream = f"{STREAM_PREFIX}:reply:{event.event_id}"
        event.payload["_reply_to"] = reply_stream

        await self.publish(event)

        # 阻塞等待回复
        try:
            messages = await self.redis.xread(
                {reply_stream: "0"}, block=int(timeout * 1000), count=1
            )
            if not messages:
                raise TimeoutError(f"Timeout waiting for reply to {event.event_id}")
            _, entries = messages[0]
            return json.loads(entries[0][1].get("payload", "{}"))
        finally:
            await self.redis.delete(reply_stream)

    # ---- 订阅 ----

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        订阅事件类型。

        handler 签名: async def handler(event: Event) -> None
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
            # 启动该事件类型的监听循环
            self._listener_tasks[event_type] = asyncio.create_task(
                self._listen(event_type)
            )

        self._handlers[event_type].append(handler)
        logger.info("eventbus.subscribed", event_type=event_type, handler=handler.__name__)

    async def _listen(self, event_type: str) -> None:
        """监听某个事件类型 Stream 的消息"""
        stream_key = f"{STREAM_PREFIX}:{event_type}"
        consumer_name = f"{self._consumer_group}-{event_type}-{uuid.uuid4().hex[:8]}"

        # 创建消费者组
        try:
            await self.redis.xgroup_create(stream_key, self._consumer_group, id="0", mkstream=True)
        except aioredis.ResponseError:
            pass  # 消费者组已存在

        while True:
            try:
                messages = await self.redis.xreadgroup(
                    groupname=self._consumer_group,
                    consumername=consumer_name,
                    streams={stream_key: ">"},
                    block=5000,
                    count=10,
                )

                if not messages:
                    continue

                for stream, entries in messages:
                    for msg_id, msg_data in entries:
                        event = Event.from_message(msg_data)
                        await self._dispatch(event_type, event)
                        await self.redis.xack(stream_key, self._consumer_group, msg_id)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("eventbus.listener_error", event_type=event_type)
                await asyncio.sleep(1)

    async def _dispatch(self, event_type: str, event: Event) -> None:
        """分发事件到所有注册的 handler，失败的消息送入死信队列"""
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        for handler in handlers:
            for attempt in range(self._max_retries):
                try:
                    await handler(event)
                    break
                except Exception:
                    if attempt == self._max_retries - 1:
                        # 所有重试失败 → 死信
                        dead_event = event.model_copy()
                        dead_event.payload["_error"] = f"Failed after {self._max_retries} attempts"
                        dead_event.payload["_handler"] = handler.__name__
                        await self.redis.xadd(
                            DEAD_LETTER_STREAM,
                            dead_event.to_message(),
                            maxlen=10_000,
                        )
                        logger.error(
                            "eventbus.dead_letter",
                            event_type=event_type,
                            event_id=event.event_id,
                            handler=handler.__name__,
                        )

    # ---- 便捷订阅（装饰器风格） ----

    def on(self, event_type: str):
        """装饰器风格订阅"""

        def decorator(handler: EventHandler):
            # 注册到待订阅列表，调用 start() 时统一连接
            if not hasattr(self, "_pending_subscriptions"):
                self._pending_subscriptions = []
            self._pending_subscriptions.append((event_type, handler))
            return handler

        return decorator

    async def start(self) -> None:
        """启动所有待注册的订阅"""
        for event_type, handler in getattr(self, "_pending_subscriptions", []):
            await self.subscribe(event_type, handler)

    async def publish_event(
        self,
        event_type: str,
        source: str,
        payload: dict[str, Any],
        target: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """便捷发布方法"""
        return await self.publish(
            Event(
                event_type=event_type,
                source=source,
                target=target,
                payload=payload,
                correlation_id=correlation_id,
            )
        )
