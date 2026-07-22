"""
结构化日志 — 基于 structlog
所有服务统一日志格式，自动附加 service_name、trace_id 等上下文
"""
from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(
    service_name: str = "agent-cluster",
    log_level: str = "INFO",
    as_json: bool = False,
) -> None:
    """
    初始化结构化日志。

    Args:
        service_name: 服务名称，会附加到每条日志
        log_level: 日志级别
        as_json: 生产环境输出 JSON 格式，开发环境输出彩色文本
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if as_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 同时配置标准库 logging 的 handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # 默认绑定 service_name
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or __name__)
