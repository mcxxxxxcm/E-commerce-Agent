"""工具注册表单元测试"""
import pytest
from shared.tools.registry import register, get_tool, get_tools_by_tag, list_tools


def test_tool_registration():
    """确保注册函数中 registry 是可变的"""
    from shared.tools import registry as reg_module
    # 导入工具文件触发注册
    import shared.tools.crm
    import shared.tools.order
    import shared.tools.product

    tools = list_tools()
    assert "query_customer" in tools
    assert "query_order" in tools
    assert "query_product" in tools


def test_get_tools_by_tag():
    import shared.tools.crm
    import shared.tools.order

    crm_tools = get_tools_by_tag("crm")
    crm_names = [getattr(t, "_tool_name", t.__name__) for t in crm_tools]
    assert "query_customer" in crm_names

    order_tools = get_tools_by_tag("order")
    order_names = [getattr(t, "_tool_name", t.__name__) for t in order_tools]
    assert "query_order" in order_names


def test_tool_schemas():
    from shared.tools.registry import get_tool_schemas
    schemas = get_tool_schemas([get_tool("query_customer")])
    assert len(schemas) > 0
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "query_customer"
