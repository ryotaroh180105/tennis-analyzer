import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("channels.line")

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


class LineChannel:
    """LINE Messaging API（push）。LINE Loginとは別チャネル ——
    友だち追加していないユーザーには送れない（10 §認証）。
    """

    def send(self, *, to_user_id: str, message: str) -> bool:
        settings = get_settings()
        if not settings.line_messaging_channel_access_token:
            logger.warning("LINE messaging token not configured; skipping send")
            return False

        try:
            resp = httpx.post(
                LINE_PUSH_URL,
                headers={
                    "Authorization": f"Bearer {settings.line_messaging_channel_access_token}",
                    "Content-Type": "application/json",
                },
                json={"to": to_user_id, "messages": [{"type": "text", "text": message}]},
                timeout=10.0,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            logger.exception("LINE push failed")
            return False
