"""
OpenTelemetry 链路追踪初始化
在微服务间传播 trace context，关联 Agent 调用链
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def init_tracing(
    service_name: str,
    otlp_endpoint: str = "http://localhost:4317",
) -> trace.Tracer:
    """初始化 OpenTelemetry 链路追踪"""
    resource = Resource.create({SERVICE_NAME: service_name})

    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def instrument_app(app, service_name: str = "agent-cluster"):
    """自动为 FastAPI 应用添加 OpenTelemetry 埋点"""
    FastAPIInstrumentor.instrument_app(app)
    RedisInstrumentor().instrument()
    # SQLAlchemyInstrumentor 在创建 engine 时调用
