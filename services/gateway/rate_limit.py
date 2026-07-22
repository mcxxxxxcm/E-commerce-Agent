"""
令牌桶限流器 — 基于 Redis 滑动窗口
"""
from __future__ import annotations

import time

from fastapi import HTTPException, Request

from shared.config import get_settings

settings = get_settings()


class TokenBucket:
    """
    简单内存令牌桶限流器。

    生产环境建议替换为 Redis 实现（支持多实例共享），或使用网关层限流（Nginx/Envoy）。
    """

    def __init__(self, rate: float = 100, burst: int = 200):
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """尝试消费 tokens。返回 True 表示允许。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False


# 全局限流器实例
_bucket = TokenBucket(
    rate=settings.rate_limit_per_second,
    burst=settings.rate_limit_burst,
)


async def rate_limit_middleware(request: Request):
    """FastAPI 中间件：对每个请求进行令牌桶限流"""
    if not _bucket.consume():
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": "1"},
        )
