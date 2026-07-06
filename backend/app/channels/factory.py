from app.channels.email import EmailChannel
from app.channels.line import LineChannel
from app.channels.noop import NoopChannel

_channels = {
    "line": LineChannel(),
    "email": EmailChannel(),
    "noop": NoopChannel(),
}


def get_channel(name: str):
    return _channels.get(name, _channels["noop"])


def notify_user(user, message: str) -> None:
    """友だち追加済みならLINE、そうでなければメール、どちらも無理ならアプリ内表示のみ
    （noop=ログのみ）に落とす（10 §認証）。呼び出し側でuser.auth_providersを見て判定する。
    """
    from app.models.user import AuthProvider  # 遅延importで循環回避

    line_provider = next(
        (p for p in user.auth_providers if p.provider == "line" and p.line_friend), None
    )
    if line_provider is not None:
        if get_channel("line").send(to_user_id=line_provider.provider_user_id, message=message):
            return

    if user.email:
        if get_channel("email").send(to_user_id=user.email, message=message):
            return

    get_channel("noop").send(to_user_id=str(user.id), message=message)
