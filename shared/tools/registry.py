"""
统一工具注册表 — 所有 Agent 共享的工具集合
支持按标签分组，Agent 按需获取工具子集
"""
from __future__ import annotations

import inspect
from collections import defaultdict
from typing import Any, Callable

from shared.logging import get_logger

logger = get_logger(__name__)

# Tool 函数签名约定: async def tool_name(params: dict) -> dict
ToolFunc = Callable[..., Any]

_registry: dict[str, ToolFunc] = {}
_tags: dict[str, list[str]] = defaultdict(list)
_tag_index: dict[str, list[str]] = defaultdict(list)


def register(
    name: str | None = None,
    tags: list[str] | None = None,
    description: str = "",
) -> Callable[[ToolFunc], ToolFunc]:
    """装饰器：将函数注册为工具"""

    def decorator(func: ToolFunc) -> ToolFunc:
        tool_name = name or func.__name__
        _registry[tool_name] = func

        for tag in tags or []:
            _tags[tool_name].append(tag)
            _tag_index[tag].append(tool_name)

        # 存储描述信息到函数属性
        func._tool_name = tool_name
        func._tool_tags = tags or []
        func._tool_description = description

        logger.debug("tool.registered", name=tool_name, tags=tags)
        return func

    return decorator


def get_tool(name: str) -> ToolFunc | None:
    """按名称获取工具"""
    return _registry.get(name)


def get_tools_by_tag(tag: str) -> list[ToolFunc]:
    """按标签获取工具列表"""
    names = _tag_index.get(tag, [])
    return [_registry[n] for n in names if n in _registry]


def get_tools_by_tags(tags: list[str]) -> list[ToolFunc]:
    """按多个标签获取工具（并集）"""
    names: set[str] = set()
    for tag in tags:
        names.update(_tag_index.get(tag, []))
    return [_registry[n] for n in names if n in _registry]


def list_tools() -> dict[str, list[str]]:
    """列出所有已注册工具及标签"""
    return {name: _tags.get(name, []) for name in _registry}


def get_tool_schemas(tools: list[ToolFunc]) -> list[dict[str, Any]]:
    """
    将工具函数转换为 OpenAI function calling 格式的 schema。
    函数签名和 docstring 自动推导参数 schema。
    """
    schemas = []
    for tool in tools:
        sig = inspect.signature(tool)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "ctx", "request"):
                continue
            param_type = "string"
            if param.annotation is int:
                param_type = "integer"
            elif param.annotation is float:
                param_type = "number"
            elif param.annotation is bool:
                param_type = "boolean"

            properties[param_name] = {"type": param_type}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        schemas.append({
            "type": "function",
            "function": {
                "name": getattr(tool, "_tool_name", tool.__name__),
                "description": getattr(tool, "_tool_description", tool.__doc__ or ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })

    return schemas


# ---------------------------------------------------------------------------
# Agent 工具集配置
# ---------------------------------------------------------------------------

AGENT_TOOL_TAGS: dict[str, list[str]] = {
    "telemarketing": ["crm", "product", "notification"],
    "live": ["product", "content", "platform"],
    "customer_service": ["order", "crm", "product", "knowledge", "notification"],
    "operations": ["analytics", "product", "crm", "competitor", "report"],
    "content": ["content", "platform", "knowledge", "product"],
    "office": ["oa", "document", "notification", "approval"],
    "product_display": ["product", "content", "platform", "image"],
}


def get_agent_tools(agent_name: str) -> list[ToolFunc]:
    """获取某个 Agent 需要的工具集"""
    tags = AGENT_TOOL_TAGS.get(agent_name, [])
    return get_tools_by_tags(tags)
