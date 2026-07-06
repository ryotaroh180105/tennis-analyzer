"""共有視聴ページ用API（認証不要。10 §API契約）。

HLSは「バックエンドがその場で署名済みセグメントURL入りのm3u8を生成して返す」方式。
リンクの寿命はtoken（revokeまで有効）、署名は再生のたびに短命発行——
S3署名URLの7日上限を「リンクの寿命」と混同しない。
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.schemas import PlaybackResponse
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import not_found
from app.models.match import VideoAsset
from app.models.share import ShareLink
from app.services import storage

router = APIRouter(prefix="/api/share", tags=["share"])


def _get_active_link_or_404(db: Session, token: str) -> ShareLink:
    link = db.query(ShareLink).filter(ShareLink.token == token, ShareLink.revoked.is_(False)).one_or_none()
    if link is None:
        raise not_found("share link")
    return link


@router.get("/{token}/playback", response_model=PlaybackResponse)
def get_playback(token: str, db: Session = Depends(get_db)) -> PlaybackResponse:
    link = _get_active_link_or_404(db, token)

    thumbnail = (
        db.query(VideoAsset)
        .filter(VideoAsset.match_id == link.match_id, VideoAsset.kind == "thumbnail")
        .order_by(desc(VideoAsset.generation))
        .first()
    )
    settings = get_settings()
    thumbnail_url = (
        storage.presign_get_url(thumbnail.r2_key, settings.share_signed_url_ttl_seconds)
        if thumbnail
        else None
    )

    return PlaybackResponse(
        playlist_url=f"/api/share/{token}/playlist.m3u8",
        thumbnail_url=thumbnail_url,
    )


@router.get("/{token}/playlist.m3u8")
def get_playlist(token: str, db: Session = Depends(get_db)) -> Response:
    link = _get_active_link_or_404(db, token)

    hls_asset = (
        db.query(VideoAsset)
        .filter(VideoAsset.match_id == link.match_id, VideoAsset.kind == "hls")
        .order_by(desc(VideoAsset.generation))
        .first()
    )
    if hls_asset is None:
        raise not_found("hls asset")

    from app.services.hls import rewrite_playlist

    body = rewrite_playlist(hls_asset.r2_key)
    return Response(content=body, media_type="application/vnd.apple.mpegurl")
