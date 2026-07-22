"""
商品展示图生成模块 — 图像生成客户端
支持 DALL-E 3 和 Stable Diffusion 两种后端
"""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()


class ImageGenBackend(ABC):
    """图像生成后端抽象基类"""

    @abstractmethod
    async def generate(self, prompt: str, num_images: int = 1) -> list[dict]:
        """
        生成图片，返回 [{"url": str, "b64_json": str | None}, ...]
        """
        ...


# ---------------------------------------------------------------------------
# DALL-E 3 后端
# ---------------------------------------------------------------------------


class DALLEBackend(ImageGenBackend):
    """OpenAI DALL-E 3 图像生成后端"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _settings.openai_api_key
        self.base_url = "https://api.openai.com/v1/images/generations"

    async def generate(self, prompt: str, num_images: int = 1) -> list[dict]:
        # DALL-E 3 一次只能生成一张，但支持并发生成
        # 对于多张需求，使用 DALL-E 2 格式或多次调用
        if num_images == 1:
            return [await self._generate_one(prompt)]

        # 并发生成多张
        import asyncio
        tasks = [self._generate_one(prompt) for _ in range(num_images)]
        return await asyncio.gather(*tasks)

    async def _generate_one(self, prompt: str) -> dict:
        """调用 DALL-E API 生成单张图片"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _settings.image_gen_model,
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "quality": "hd",
                    "style": "natural",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            image_data = data["data"][0]
            return {
                "url": image_data.get("url", ""),
                "b64_json": image_data.get("b64_json"),
            }


# ---------------------------------------------------------------------------
# Stable Diffusion 后端
# ---------------------------------------------------------------------------


class StabilityBackend(ImageGenBackend):
    """Stability AI (Stable Diffusion) 图像生成后端"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or _settings.openai_api_key  # 用 openai_api_key 占位
        self.base_url = "https://api.stability.ai/v2beta/stable-image/generate/core"

    async def generate(self, prompt: str, num_images: int = 1) -> list[dict]:
        import asyncio
        tasks = [self._generate_one(prompt) for _ in range(num_images)]
        return await asyncio.gather(*tasks)

    async def _generate_one(self, prompt: str) -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                },
                files={"none": ""},
                data={
                    "prompt": prompt,
                    "output_format": "png",
                    "style_preset": "photographic",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            base64_str = data.get("image", "")
            return {
                "url": "",
                "b64_json": base64_str,
            }


# ---------------------------------------------------------------------------
# 后端工厂
# ---------------------------------------------------------------------------


def get_image_gen_backend() -> ImageGenBackend:
    """根据配置返回对应的图像生成后端"""
    provider = _settings.image_gen_provider
    if provider == "stability":
        return StabilityBackend()
    return DALLEBackend()


async def download_generated_image(url: str) -> bytes:
    """下载生成的图片"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content
