from .douyin import DouyinAdapter
from .xiaohongshu import XiaohongshuAdapter
from .taobao import TaobaoAdapter

PLATFORM_ADAPTERS = {
    "douyin": DouyinAdapter,
    "xiaohongshu": XiaohongshuAdapter,
    "taobao": TaobaoAdapter,
}

__all__ = ["DouyinAdapter", "XiaohongshuAdapter", "TaobaoAdapter", "PLATFORM_ADAPTERS"]
