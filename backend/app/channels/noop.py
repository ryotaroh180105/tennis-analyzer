import logging

logger = logging.getLogger("channels.noop")


class NoopChannel:
    """M2〜M4のプレースホルダ。ログに残すだけで実送信はしない（10 §ジョブフロー）。"""

    def send(self, *, to_user_id: str, message: str) -> bool:
        logger.info("noop channel: would send to %s: %s", to_user_id, message)
        return True
