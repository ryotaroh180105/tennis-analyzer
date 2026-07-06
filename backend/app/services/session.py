"""Redisにserver-side session（30日、10 §認証）。DBにsessionsテーブルは持たない。"""

import json
import secrets
import uuid

from app.core.config import get_settings
from app.services.redis_client import get_redis

SESSION_PREFIX = "session:"


def create_session(user_id: uuid.UUID) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    get_redis().setex(
        f"{SESSION_PREFIX}{token}",
        settings.session_ttl_days * 24 * 3600,
        json.dumps({"user_id": str(user_id)}),
    )
    return token


def read_session(token: str) -> uuid.UUID | None:
    raw = get_redis().get(f"{SESSION_PREFIX}{token}")
    if raw is None:
        return None
    data = json.loads(raw)
    return uuid.UUID(data["user_id"])


def destroy_session(token: str) -> None:
    get_redis().delete(f"{SESSION_PREFIX}{token}")
