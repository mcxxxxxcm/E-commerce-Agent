"""
电商运营 Deep Agent — 自主规划型 Agent

为什么用 Deep Agent：
- 需要自主规划：分析数据 → 发现问题 → 制定策略 → 执行调整
- 需要子 Agent：数据分析子Agent + 策略生成子Agent
- 对话长且复杂（20+轮），需要上下文管理
- 不追求实时，离线分析任务
"""
from __future__ import annotations

from langchain_anthropic import ChatAnthropic

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()


def create_ops_agent(tools: list):
    """
    创建运营 Deep Agent。

    使用方式:
        agent = create_ops_agent(tools)
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": "分析本周销售数据并给出优化建议"}]
        })
    """
    # 生产环境使用 deepagents 库:
    # from deepagents import create_deep_agent
    # return create_deep_agent(
    #     model=f"anthropic:{_settings.default_model}",
    #     tools=tools,
    #     system_prompt=OPS_SYSTEM_PROMPT,
    # )

    # 开发环境使用 LangGraph create_agent 作为替代
    from langgraph.prebuilt import create_react_agent

    llm = ChatAnthropic(
        model=_settings.default_model,
        api_key=_settings.anthropic_api_key,
        temperature=0.2,
    )

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=OPS_SYSTEM_PROMPT,
    )


OPS_SYSTEM_PROMPT = """你是一个资深的电商运营专家智能体。

## 能力范围
1. **销售数据分析**：分析销售额、订单量、转化率、客单价等核心指标
2. **竞品分析**：分析竞品定价、卖点、营销策略
3. **定价策略**：根据市场数据和成本结构，建议最优定价
4. **详情页优化**：分析转化漏斗，给出详情页优化建议
5. **报告生成**：自动生成日报/周报/月报
6. **促销策划**：根据数据制定促销方案

## 工作方式
- 收到任务后，先分析数据，再制定策略，最后给出可执行的建议
- 需要查询数据时主动使用工具
- 发现异常数据时重点标注并分析原因
- 给出的建议要有数据支撑，包含预期效果

## 限制
- 价格调整建议不能超过成本价的 20% 浮动
- 促销折扣不得低于 7 折（除非清仓场景）
- 所有对外发布的决策需要人工审核
"""
