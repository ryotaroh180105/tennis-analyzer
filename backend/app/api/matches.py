"""試合・区間・共有 API（10 §API契約）。"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import (
    MatchCreateRequest,
    MatchCreateResponse,
    MatchResponse,
    PlaybackResponse,
    ProgressInfo,
    SegmentEffective,
    SegmentRaw,
    SegmentsPatchRequest,
    SegmentsResponse,
    ShareLinkResponse,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import conflict, not_found, rate_limited, validation_error
from app.jobs.enqueue import enqueue_precheck, enqueue_recut
from app.models.job import AnalysisJob, JobStage
from app.models.match import Match, MatchStatus, VideoAsset
from app.models.segment import Segment, SegmentOp, SegmentSource
from app.models.share import ShareLink
from app.models.upload import Upload, UploadStatus
from app.models.user import User
from app.services import segments as segments_service
from app.services import storage

router = APIRouter(prefix="/api", tags=["matches"])

# stage重み（10 §API契約: progress合成）
STAGE_WEIGHTS = {"precheck": 10, "ingest": 25, "analyze": 45, "edit": 20}
STAGE_ORDER = ["precheck", "ingest", "analyze", "edit"]


def _get_match_or_404(db: Session, user: User, match_id: uuid.UUID) -> Match:
    match = db.get(Match, match_id)
    if match is None or match.user_id != user.id:
        raise not_found("match")
    return match


def _compute_progress(db: Session, match: Match) -> ProgressInfo:
    if match.status == MatchStatus.done:
        return ProgressInfo(stage=None, pct=100)
    if match.status == MatchStatus.failed:
        return ProgressInfo(stage=None, pct=0)

    jobs = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.match_id == match.id)
        .order_by(desc(AnalysisJob.attempt))
        .all()
    )
    latest_by_stage: dict[str, AnalysisJob] = {}
    for job in jobs:
        if job.stage.value not in latest_by_stage:
            latest_by_stage[job.stage.value] = job

    completed_pct = 0.0
    current_stage = STAGE_ORDER[0]
    for stage in STAGE_ORDER:
        job = latest_by_stage.get(stage)
        weight = STAGE_WEIGHTS[stage]
        if job is None:
            current_stage = stage
            break
        if job.status.value == "succeeded":
            completed_pct += weight
            continue
        current_stage = stage
        completed_pct += weight * (job.progress / 100)
        break

    return ProgressInfo(stage=current_stage, pct=round(completed_pct))


def _serialize_match(db: Session, match: Match) -> MatchResponse:
    # 現行世代のみ返す（kindごとの最大generation）
    assets = (
        db.query(VideoAsset)
        .filter(VideoAsset.match_id == match.id)
        .order_by(VideoAsset.kind, desc(VideoAsset.generation))
        .all()
    )
    seen_kinds: set[str] = set()
    current_assets = []
    for a in assets:
        if a.kind.value in seen_kinds:
            continue
        seen_kinds.add(a.kind.value)
        current_assets.append(
            {"kind": a.kind.value, "generation": a.generation, "duration_s": a.duration_s}
        )

    return MatchResponse(
        id=match.id,
        title=match.title,
        status=match.status.value,
        failure_reason=match.failure_reason,
        preflight_report=match.preflight_report,
        assets=current_assets,
        progress=_compute_progress(db, match),
        created_at=match.created_at,
    )


@router.post("/matches", response_model=MatchCreateResponse)
def create_match(
    body: MatchCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatchCreateResponse:
    settings = get_settings()

    # 10本/日のabuse検知（10 §共通事項）
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent_count = (
        db.query(Match)
        .filter(Match.user_id == user.id, Match.created_at >= since)
        .count()
    )
    if recent_count >= settings.upload_daily_limit:
        raise rate_limited("daily upload limit reached")

    upload = db.get(Upload, body.upload_id)
    if upload is None or upload.user_id != user.id:
        raise not_found("upload")
    if upload.status != UploadStatus.completed or upload.used_by_match:
        raise conflict("upload is not completed or already used")

    match = Match(user_id=user.id, upload_id=upload.id, title=body.title, status=MatchStatus.queued)
    db.add(match)
    db.flush()

    # original行はuploads.r2_keyを参照して作成する（コピーしない、10）
    db.add(VideoAsset(match_id=match.id, kind="original", generation=0, r2_key=upload.r2_key))
    upload.used_by_match = True
    db.commit()
    db.refresh(match)

    enqueue_precheck(str(match.id))

    return MatchCreateResponse(id=match.id, status=match.status.value)


@router.get("/matches", response_model=list[MatchResponse])
def list_matches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MatchResponse]:
    matches = (
        db.query(Match)
        .filter(Match.user_id == user.id)
        .order_by(desc(Match.created_at))
        .all()
    )
    return [_serialize_match(db, m) for m in matches]


@router.get("/matches/{match_id}", response_model=MatchResponse)
def get_match(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatchResponse:
    match = _get_match_or_404(db, user, match_id)
    return _serialize_match(db, match)


@router.get("/matches/{match_id}/playback", response_model=PlaybackResponse)
def get_match_playback(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaybackResponse:
    """自分の試合詳細画面での再生用（共有ページと同じ署名m3u8方式を認証付きで提供）。"""
    match = _get_match_or_404(db, user, match_id)
    settings = get_settings()

    thumbnail = (
        db.query(VideoAsset)
        .filter(VideoAsset.match_id == match.id, VideoAsset.kind == "thumbnail")
        .order_by(desc(VideoAsset.generation))
        .first()
    )
    thumbnail_url = (
        storage.presign_get_url(thumbnail.r2_key, settings.share_signed_url_ttl_seconds)
        if thumbnail
        else None
    )
    return PlaybackResponse(playlist_url=f"/api/matches/{match_id}/playlist.m3u8", thumbnail_url=thumbnail_url)


@router.get("/matches/{match_id}/playlist.m3u8")
def get_match_playlist(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    match = _get_match_or_404(db, user, match_id)
    hls_asset = (
        db.query(VideoAsset)
        .filter(VideoAsset.match_id == match.id, VideoAsset.kind == "hls")
        .order_by(desc(VideoAsset.generation))
        .first()
    )
    if hls_asset is None:
        raise not_found("hls asset")

    from app.services.hls import rewrite_playlist

    body = rewrite_playlist(hls_asset.r2_key)
    return Response(content=body, media_type="application/vnd.apple.mpegurl")


@router.get("/matches/{match_id}/segments", response_model=SegmentsResponse)
def get_segments(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SegmentsResponse:
    match = _get_match_or_404(db, user, match_id)
    rows = db.query(Segment).filter(Segment.match_id == match.id).all()
    effective = segments_service.compute_effective(rows)
    revision = segments_service.current_revision(rows)
    return SegmentsResponse(
        revision=revision,
        effective=[SegmentEffective(**e) for e in effective],
        raw=[
            SegmentRaw(
                id=r.id,
                revision=r.revision,
                op=r.op.value,
                base_segment_id=r.base_segment_id,
                start_s=r.start_s,
                end_s=r.end_s,
                source=r.source.value,
            )
            for r in rows
        ],
    )


@router.patch("/matches/{match_id}/segments", response_model=SegmentsResponse)
def patch_segments(
    match_id: uuid.UUID,
    body: SegmentsPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SegmentsResponse:
    match = _get_match_or_404(db, user, match_id)

    # status=done のときのみ受付（解析・編集中は409。10）
    if match.status != MatchStatus.done:
        raise conflict("segments can only be edited when the match is done")

    rows = db.query(Segment).filter(Segment.match_id == match.id).all()
    current_rev = segments_service.current_revision(rows)
    if body.base_revision != current_rev:
        raise conflict(
            "segments have been modified by another session",
            {"current_revision": current_rev},
        )

    original_asset = (
        db.query(VideoAsset)
        .filter(VideoAsset.match_id == match.id, VideoAsset.kind == "normalized")
        .order_by(desc(VideoAsset.generation))
        .first()
    )
    duration_s = original_asset.duration_s if original_asset else None

    new_revision = current_rev + 1
    for op_req in body.ops:
        segments_service.validate_op(
            op_req.op, op_req.start_s, op_req.end_s, op_req.base_segment_id, duration_s
        )
        db.add(
            Segment(
                match_id=match.id,
                revision=new_revision,
                op=SegmentOp(op_req.op),
                base_segment_id=op_req.base_segment_id,
                start_s=op_req.start_s,
                end_s=op_req.end_s,
                source=SegmentSource.user,
            )
        )
    db.commit()

    rows = db.query(Segment).filter(Segment.match_id == match.id).all()
    effective = segments_service.compute_effective(rows)
    return SegmentsResponse(
        revision=new_revision,
        effective=[SegmentEffective(**e) for e in effective],
        raw=[
            SegmentRaw(
                id=r.id,
                revision=r.revision,
                op=r.op.value,
                base_segment_id=r.base_segment_id,
                start_s=r.start_s,
                end_s=r.end_s,
                source=r.source.value,
            )
            for r in rows
        ],
    )


@router.post("/matches/{match_id}/recut", status_code=202)
def recut(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    match = _get_match_or_404(db, user, match_id)
    if match.status != MatchStatus.done:
        raise conflict("recut can only be requested when the match is done")

    match.status = MatchStatus.editing
    db.commit()
    enqueue_recut(str(match.id))
    return {"status": match.status.value}


@router.post("/matches/{match_id}/share", response_model=ShareLinkResponse)
def create_share_link(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareLinkResponse:
    match = _get_match_or_404(db, user, match_id)

    # matchあたり有効リンク1本（再発行で旧行をrevoked=true、10）
    db.query(ShareLink).filter(ShareLink.match_id == match.id, ShareLink.revoked.is_(False)).update(
        {"revoked": True}
    )
    link = ShareLink(match_id=match.id, token=secrets.token_urlsafe(32))
    db.add(link)
    db.commit()

    return ShareLinkResponse(url=f"/s/{link.token}")


@router.delete("/matches/{match_id}/share", status_code=204)
def revoke_share_link(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    match = _get_match_or_404(db, user, match_id)
    db.query(ShareLink).filter(ShareLink.match_id == match.id, ShareLink.revoked.is_(False)).update(
        {"revoked": True}
    )
    db.commit()
