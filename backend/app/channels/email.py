import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("channels.email")

RESEND_URL = "https://api.resend.com/emails"


class EmailChannel:
    """メール送信基盤はResend（10 §認証の申し送り）。"""

    def send(self, *, to_user_id: str, message: str) -> bool:
        settings = get_settings()
        if not settings.resend_api_key:
            logger.warning("Resend API key not configured; skipping send")
            return False

        try:
            resp = httpx.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [to_user_id],
                    "subject": "Tennis Analyzer",
                    "text": message,
                },
                timeout=10.0,
            )
            return resp.status_code < 300
        except httpx.HTTPError:
            logger.exception("Email send failed")
            return False
