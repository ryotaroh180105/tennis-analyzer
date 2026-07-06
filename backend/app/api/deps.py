from collections.abc import Generator

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import unauthorized
from app.models.user import AuthProvider, User
from app.services.session import read_session

SESSION_COOKIE = "session"


def _get_or_create_dev_user(db: Session) -> User:
    """M1〜M4：認証なしで動かすための固定devユーザー（10 §API契約）。"""
    provider = (
        db.query(AuthProvider)
        .filter(AuthProvider.provider == "dev", AuthProvider.provider_user_id == "dev-user")
        .one_or_none()
    )
    if provider is not None:
        return provider.user

    user = User(display_name="Dev User", email=None, locale="ja")
    db.add(user)
    db.flush()
    provider = AuthProvider(user_id=user.id, provider="dev", provider_user_id="dev-user")
    db.add(provider)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    settings = get_settings()

    if session_token:
        user_id = read_session(session_token)
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                return user

    if settings.dev_auto_user:
        return _get_or_create_dev_user(db)

    raise unauthorized()


DbSession = Depends(get_db)
CurrentUser = Depends(get_current_user)
