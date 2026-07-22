"""
健康检查脚本 — 检查所有 Agent 和基础设施服务状态
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from shared.config import get_settings

settings = get_settings()

SERVICES = {
    **settings.agent_urls,
    "postgres": f"http://localhost:{settings.postgres_port}",
    "redis": f"http://localhost:{settings.redis_port}",
}


async def check_service(name: str, url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            health_url = f"{url}/health" if "localhost" not in url else url
            resp = await client.get(f"{url}/health")
            return {"name": name, "status": "healthy" if resp.status_code == 200 else "degraded", "status_code": resp.status_code}
    except Exception as exc:
        return {"name": name, "status": "unreachable", "error": str(exc)}


async def main():
    print("=" * 60)
    print("Agent Cluster Health Check")
    print("=" * 60)

    tasks = [check_service(name, url) for name, url in SERVICES.items()]
    results = await asyncio.gather(*tasks)

    healthy = 0
    unhealthy = 0

    for result in results:
        icon = "✓" if result["status"] == "healthy" else "✗"
        print(f"  {icon} {result['name']:<20} {result['status']}")
        if result["status"] == "healthy":
            healthy += 1
        else:
            unhealthy += 1
            if "error" in result:
                print(f"      Error: {result['error']}")

    print("-" * 60)
    print(f"Total: {len(results)} | Healthy: {healthy} | Unhealthy: {unhealthy}")
    print("=" * 60)

    return unhealthy == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
