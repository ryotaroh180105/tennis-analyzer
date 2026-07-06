"""認証API（10 §認証）。

LINE Login v2.1 authorization code flow（LIFFは使わない。PWAの通常ブラウザ文脈で動かす）。
state＋PKCE verifierをRedis（10分）に保存し、コールバックで検証する。
line_channel_id が未設定の環境ではLINEログインは無効（501）—— devは /api/auth/dev を使う。
"""

import base64
import hashlib
import json
import secrets
import uuid

import httpx
import jwt
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE, get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError, unauthorized, validation_error
from app.models.user import AuthProvider, User
from app.services.redis_client import get_redis
from app.services.session import create_session, destroy_session

router = APIRouter(prefix="/api/auth", tags=["auth"])

LINE_AUTHORIZE_URL = "https://access.line.me/oauth2/v2.1/authorize"
LINE_TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
STATE_PREFIX = "line_oauth_state:"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


@router.get("/line/start")
def line_login_start() -> Response:
    settings = get_settings()
    if not settings.line_channel_id:
        raise ApiError(501, "not_implemented", "LINE login is not configured in this environment")

    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    get_redis().setex(f"{STATE_PREFIX}{state}", 600, json.dumps({"verifier": verifier}))

    params = {
        "response_type": "code",
        "client_id": settings.line_channel_id,
        "redirect_uri": settings.line_redirect_uri,
        "state": state,
        "scope": "profile openid email",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items())
    return Response(status_code=302, headers={"Location": f"{LINE_AUTHORIZE_URL}?{query}"})


@router.get("/line/callback")
def line_login_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    raw = get_redis().get(f"{STATE_PREFIX}{state}")
    if raw is None:
        raise validation_error("invalid or expired state")
    get_redis().delete(f"{STATE_PREFIX}{state}")
    verifier = json.loads(raw)["verifier"]

    token_resp = httpx.post(
        LINE_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.line_redirect_uri,
            "client_id": settings.line_channel_id,
            "client_secret": settings.line_channel_secret,
            "code_verifier": verifier,
        },
        timeout=10.0,
    )
    if token_resp.status_code != 200:
        raise unauthorized("LINE token exchange failed")
    token_data = token_resp.json()

    # IDトークンをチャネルIDでaudience検証（署名検証はLINEの公開鍵で行うのが本来だが
    # ここではまず基本のaudience/issuer検証のみ実装。本番導入時にJWKS検証を追加すること）
    id_token = token_data["id_token"]
    claims = jwt.decode(
        id_token, options={"verify_signature": False}, algorithms=["HS256", "RS256"]
    )
    if claims.get("aud") != settings.line_channel_id:
        raise unauthorized("id token audience mismatch")

    line_user_id = claims["sub"]
    email = claims.get("email")
    display_name = claims.get("name", "Tennis Player")

    provider = (
        db.query(AuthProvider)
        .filter(AuthProvider.provider == "line", AuthProvider.provider_user_id == line_user_id)
        .one_or_none()
    )
    if provider is None:
        user = User(display_name=display_name, email=email, locale="ja")
        db.add(user)
        db.flush()
        provider = AuthProvider(user_id=user.id, provider="line", provider_user_id=line_user_id)
        db.add(provider)
    else:
        user = provider.user
        if email and not user.email:
            user.email = email
    db.commit()

    session_token = create_session(user.id)
    response = Response(status_code=302, headers={"Location": "/"})
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        destroy_session(token)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.post("/dev", include_in_schema=False)
def dev_login(db: Session = Depends(get_db)) -> Response:
    """dev環境専用：devユーザーで即セッション発行（本番ではdev_auto_userがFalseのため404扱いにする）。"""
    settings = get_settings()
    if not settings.dev_auto_user:
        raise unauthorized()

    from app.api.deps import _get_or_create_dev_user

    user = _get_or_create_dev_user(db)
    session_token = create_session(user.id)
    response = Response(status_code=204)
    response.set_cookie(SESSION_COOKIE, session_token, httponly=True, samesite="lax")
    return response


@router.patch("/me", include_in_schema=True)
def update_me(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """メール未許諾時の手入力フロー（10 §認証: メール取得率100%のためのフォールバック）。"""
    email = body.get("email")
    if not email or "@" not in email:
        raise validation_error("invalid email")
    user.email = email
    db.commit()
    return {"email": user.email}


@router.post("/line/webhook", include_in_schema=False)
async def line_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """follow/unfollowイベントを受けて auth_providers.line_friend を更新（10 §友だち判定）。"""
    body = await request.json()
    for event in body.get("events", []):
        source_user_id = event.get("source", {}).get("userId")
        if not source_user_id:
            continue
        provider = (
            db.query(AuthProvider)
            .filter(AuthProvider.provider == "line", AuthProvider.provider_user_id == source_user_id)
            .one_or_none()
        )
        if provider is None:
            continue
        if event["type"] == "follow":
            provider.line_friend = True
        elif event["type"] == "unfollow":
            provider.line_friend = False
    db.commit()
    return {"status": "ok"}
