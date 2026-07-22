"""
商品展示图生成模块 — 图片上传与存储
"""
from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from shared.config import get_settings
from shared.logging import get_logger

logger = get_logger(__name__)

_settings = get_settings()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


class StorageError(Exception):
    """存储异常"""
    pass


def _validate_image(filename: str, file_size: int) -> None:
    """校验图片格式和大小"""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError(f"不支持的图片格式: {ext}，仅支持 jpg/png/webp")
    if file_size > MAX_FILE_SIZE:
        raise StorageError(f"图片大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)")


def _ensure_storage_dir(image_id: str) -> Path:
    """确保存储目录存在"""
    base = Path(_settings.image_storage_path)
    image_dir = base / image_id
    image_dir.mkdir(parents=True, exist_ok=True)
    return image_dir


async def save_upload(image: UploadFile) -> dict:
    """保存上传的商品原图，返回 image_id 和路径信息"""
    file_size = image.size or 0
    _validate_image(image.filename or "unknown.jpg", file_size)

    image_id = str(uuid.uuid4())
    ext = Path(image.filename).suffix.lower() if image.filename else ".jpg"
    image_dir = _ensure_storage_dir(image_id)

    original_path = image_dir / f"original{ext}"
    content = await image.read()
    async with aiofiles.open(original_path, "wb") as f:
        await f.write(content)

    logger.info("product_display.image_saved", image_id=image_id, size=file_size)

    return {
        "image_id": image_id,
        "original_path": str(original_path),
        "ext": ext,
        "size": file_size,
    }


async def save_generated_image(image_id: str, image_data: bytes, index: int = 0) -> str:
    """保存生成的展示图，返回文件路径"""
    image_dir = _ensure_storage_dir(image_id)
    path = image_dir / f"display_{index}.png"
    async with aiofiles.open(path, "wb") as f:
        await f.write(image_data)
    return str(path)
