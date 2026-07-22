"""
SSE 流式输出 — 客服 Agent 的流式响应
"""
from __future__ import annotations

import json
from typing import AsyncGenerator


async def stream_response(content: str, chunk_size: int = 5) -> AsyncGenerator[str, None]:
    """
    将文本以 SSE 格式逐块输出。

    使用方式（FastAPI）:
        return StreamingResponse(
            stream_response(content),
            media_type="text/event-stream",
        )
    """
    for i in range(0, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        yield f"data: {json.dumps({'content': chunk, 'done': False}, ensure_ascii=False)}\n\n"

    yield f"data: {json.dumps({'content': '', 'done': True}, ensure_ascii=False)}\n\n"
