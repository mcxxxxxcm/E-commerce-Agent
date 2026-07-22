"""测试公共配置"""
import pytest


@pytest.fixture
def event_bus():
    """返回一个 mock EventBus"""
    from unittest.mock import AsyncMock
    return AsyncMock()


@pytest.fixture
def settings():
    from shared.config import get_settings
    return get_settings()
