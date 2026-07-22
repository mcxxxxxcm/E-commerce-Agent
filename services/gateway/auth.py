"""
API 网关认证 — JWT + API Key 双重认证
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from shared.config import get_settings

settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """生成 JWT Token"""
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    return jwt.encode(
        {"sub": subject, "exp": expire, "iat": datetime.now(UTC)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str) -> dict:
    """验证 JWT Token"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


# 内部服务间通信的 API Key（简单共享秘钥模式）
INTERNAL_API_KEYS: set[str] = set()


def register_api_key(key: str) -> None:
    INTERNAL_API_KEYS.add(key)


async def authenticate(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
) -> dict:
    """
    双层认证中间件：
    - JWT Token（外部用户）
    - API Key（内部服务间调用）
    """
    # 方式1: API Key（内部服务）
    if api_key and api_key in INTERNAL_API_KEYS:
        return {"sub": "internal", "auth_method": "api_key"}

    # 方式2: JWT Token（外部用户）
    if credentials:
        return verify_token(credentials.credentials)

    raise HTTPException(status_code=401, detail="Authentication required")
