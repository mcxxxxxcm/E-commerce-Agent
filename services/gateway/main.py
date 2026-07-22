"""
统一 API 网关 — 所有 Agent 流量的入口
功能：认证、限流、路由分发、健康检查聚合、指标暴露
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import PlainTextResponse

from shared.config import get_settings
from shared.logging import get_logger, setup_logging
from shared.tracing import init_tracing, instrument_app

from .auth import authenticate, create_access_token
from .rate_limit import rate_limit_middleware
from .routes.proxy import proxy_to_agent

logger = get_logger(__name__)
_settings = get_settings()

# Prometheus 指标
REQUEST_COUNT = Counter("gateway_requests_total", "请求总数", ["agent", "method", "status"])
REQUEST_LATENCY = Histogram("gateway_request_latency_seconds", "请求延迟", ["agent"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(service_name="gateway", log_level=_settings.log_level, as_json=False)
    logger.info("gateway.started", port=_settings.gateway_port)
    yield
    logger.info("gateway.stopped")


app = FastAPI(
    title="Agent Cluster Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流中间件
app.middleware("http")(rate_limit_middleware)

# OpenTelemetry
tracer = init_tracing("gateway", _settings.otel_exporter_otlp_endpoint)
instrument_app(app, "gateway")


# ---------------------------------------------------------------------------
# 聚合健康检查
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {
        "service": "gateway",
        "status": "healthy",
        "agents": list(_settings.agent_urls.keys()),
    }


@app.get("/health/{agent_name}")
async def agent_health(agent_name: str) -> dict:
    """检查指定 Agent 的健康状态"""
    import httpx
    url = _settings.agent_urls.get(agent_name)
    if not url:
        return {"agent": agent_name, "status": "not_found"}

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{url}/health")
            return {"agent": agent_name, "status": "healthy", "detail": resp.json()}
    except Exception:
        return {"agent": agent_name, "status": "unreachable"}


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
async def login(request: LoginRequest) -> dict:
    """用户登录，获取 JWT Token"""
    # 生产环境替换为实际的用户验证逻辑
    if not request.username or not request.password:
        from fastapi import HTTPException
        raise HTTPException(400, "Username and password required")

    token = create_access_token(subject=request.username)
    return {"access_token": token, "token_type": "bearer"}


# ---------------------------------------------------------------------------
# Agent 路由代理
# ---------------------------------------------------------------------------

@app.api_route("/{agent_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def route_to_agent(
    agent_name: str,
    path: str = "",
    request: Request = None,
    _user: dict = Depends(authenticate),
):
    """核心路由：将请求代理到对应的 Agent 微服务"""
    # 构建完整路径
    request.scope["path"] = f"/{path}"
    return await proxy_to_agent(request, agent_name)


# ---------------------------------------------------------------------------
# 直连路由（不需要 /{agent_name}/ 前缀的场景）
# ---------------------------------------------------------------------------

@app.post("/task")
async def create_task(request: Request, _user: dict = Depends(authenticate)):
    """快捷路由：直接创建编排任务 → Supervisor"""
    request.scope["path"] = "/task"
    return await proxy_to_agent(request, "supervisor")


@app.post("/chat")
async def chat(request: Request, _user: dict = Depends(authenticate)):
    """快捷路由：直接调用客服"""
    request.scope["path"] = "/chat"
    return await proxy_to_agent(request, "customer_service")


# ---------------------------------------------------------------------------
# Prometheus 指标
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点"""
    return PlainTextResponse(generate_latest(), media_type="text/plain")


# ---------------------------------------------------------------------------
# 管理接口
# ---------------------------------------------------------------------------

@app.get("/admin/agents")
async def admin_list_agents() -> dict:
    """管理：列出所有 Agent 及路由"""
    return {
        "agents": {
            name: {
                "url": url,
                "health": f"/health/{name}",
            }
            for name, url in _settings.agent_urls.items()
        }
    }


@app.post("/admin/events")
async def admin_publish_event(event_type: str, payload: dict, source: str = "gateway"):
    """管理：手动发布事件（用于调试和运维）"""
    from shared.eventbus import EventBus
    bus = EventBus(redis_url=_settings.redis_url)
    await bus.connect()
    try:
        msg_id = await bus.publish_event(
            event_type=event_type,
            source=source,
            payload=payload,
        )
        return {"status": "published", "msg_id": msg_id}
    finally:
        await bus.disconnect()
