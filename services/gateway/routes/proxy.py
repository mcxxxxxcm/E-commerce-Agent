"""
反向代理 — 将请求路由到对应的 Agent 服务
"""
from __future__ import annotations

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Agent 路由映射
ROUTE_MAP = {
    "/supervisor": settings.supervisor_url,
    "/telemarketing": settings.telemarketing_url,
    "/live": settings.live_url,
    "/cs": settings.customer_service_url,
    "/operations": settings.operations_url,
    "/content": settings.content_url,
    "/office": settings.office_url,
    "/product-display": settings.product_display_url,
}


async def proxy_to_agent(request: Request, agent_name: str):
    """将请求代理到目标 Agent"""
    target_url = ROUTE_MAP.get(f"/{agent_name}")
    if target_url is None:
        raise HTTPException(404, f"Agent '{agent_name}' not found")

    # 构建目标 URL：去掉网关前缀
    path = request.url.path.replace(f"/{agent_name}", "", 1) or "/"
    url = f"{target_url}{path}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            # 读取请求体
            body = await request.body()

            # 转发请求
            resp = await client.request(
                method=request.method,
                url=url,
                headers={
                    k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "content-length")
                },
                content=body,
                params=request.query_params,
            )

            # 如果是流式响应，转发 SSE
            if "text/event-stream" in resp.headers.get("content-type", ""):
                return StreamingResponse(
                    resp.aiter_bytes(),
                    media_type="text/event-stream",
                    headers=dict(resp.headers),
                    status_code=resp.status_code,
                )

            from fastapi.responses import Response
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("content-type"),
            )

        except httpx.ConnectError:
            logger.error("gateway.agent_unreachable", agent=agent_name, url=url)
            raise HTTPException(503, f"Agent '{agent_name}' is not available")
        except httpx.TimeoutException:
            raise HTTPException(504, f"Agent '{agent_name}' request timed out")
