"""
统一配置管理 — 基于 Pydantic Settings
所有环境变量集中定义，类型安全，支持 .env 文件加载
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 文件加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 环境 ---
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- 数据库 ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "agent_cluster"
    postgres_user: str = "agent"
    postgres_password: str = "change-me-in-production"
    database_url: str = ""
    database_url_sync: str = ""

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # --- LLM ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_model: str = "claude-sonnet-4-6"
    fast_model: str = "claude-haiku-4-5"
    vision_model: str = "claude-sonnet-4-6"

    # --- Embedding ---
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # --- 网关 ---
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    gateway_workers: int = 4

    # --- JWT ---
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # --- 限流 ---
    rate_limit_per_second: int = 100
    rate_limit_burst: int = 200

    # --- 服务发现 ---
    supervisor_url: str = "http://localhost:8001"
    telemarketing_url: str = "http://localhost:8002"
    live_url: str = "http://localhost:8003"
    customer_service_url: str = "http://localhost:8004"
    operations_url: str = "http://localhost:8005"
    content_url: str = "http://localhost:8006"
    office_url: str = "http://localhost:8007"
    product_display_url: str = "http://localhost:8008"

    # --- 图像生成 ---
    image_gen_provider: Literal["dalle", "stability"] = "dalle"
    image_gen_model: str = "dall-e-3"
    image_storage_path: str = "./data/product-images"

    # --- 可观测性 ---
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    prometheus_port: int = 9090

    # --- 通知 ---
    feishu_webhook_url: str = ""
    dingtalk_webhook_url: str = ""

    @property
    def redis_url(self) -> str:
        pw = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{pw}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def agent_urls(self) -> dict[str, str]:
        return {
            "supervisor": self.supervisor_url,
            "telemarketing": self.telemarketing_url,
            "live": self.live_url,
            "customer_service": self.customer_service_url,
            "operations": self.operations_url,
            "content": self.content_url,
            "office": self.office_url,
            "product_display": self.product_display_url,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
