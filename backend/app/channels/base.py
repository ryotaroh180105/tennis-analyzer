"""通知チャネルの共通インターフェース（10 §API契約、07 §チャネル抽象）。

LINEをスキーマ・コードレベルで固定しない — 海外展開時にWhatsApp/Push/Emailへ
差し替える前提のアダプタ設計。M2〜M4はnoop、M5でline/emailを有効化する。
"""

from typing import Protocol


class Channel(Protocol):
    def send(self, *, to_user_id: str, message: str) -> bool:
        """送信できたら True。到達不能（未登録・未友だち等）なら False を返す（例外にしない）。"""
        ...
