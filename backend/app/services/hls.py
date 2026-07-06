"""HLS m3u8の署名URL書き換え（share.pyとmatches.pyで共用）。"""

from app.core.config import get_settings
from app.services import storage


def rewrite_playlist(hls_key: str) -> str:
    settings = get_settings()
    raw = storage.get_object_bytes(hls_key).decode("utf-8")
    base_prefix = hls_key.rsplit("/", 1)[0]

    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            seg_key = f"{base_prefix}/{stripped}"
            lines.append(storage.presign_get_url(seg_key, settings.share_signed_url_ttl_seconds))
        else:
            lines.append(line)
    return "\n".join(lines)
