"""マルチパートアップロードAPI（10 §アップロードAPI）。

再開可能性が最重要：完了時のETagはクライアントに持たせず、
サーバーがR2 ListPartsから取得してCompleteMultipartUploadを実行する
（クライアント再起動でETagを失っても再開できる、というRound2の指摘への回答）。
"""

import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import (
    UploadCreateRequest,
    UploadCreateResponse,
    UploadPartsRequest,
    UploadPartsResponse,
    UploadStatusResponse,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import not_found, payload_too_large, validation_error
from app.models.upload import Upload, UploadStatus
from app.models.user import User
from app.services import storage

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("", response_model=UploadCreateResponse)
def create_upload(
    body: UploadCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadCreateResponse:
    settings = get_settings()

    if not body.content_type.startswith("video/"):
        raise validation_error("content_type must be video/*", {"content_type": body.content_type})

    if body.total_size > settings.upload_max_bytes:
        raise payload_too_large(
            f"total_size exceeds the {settings.upload_max_bytes} byte limit"
        )

    # バケットの存在確認はアプリ起動時に1回だけ行う（main.pyのlifespan）。
    # 毎リクエストでのhead_bucket/create_bucketは不要なレイテンシと失敗点を増やすため避ける。
    key = storage.build_upload_key(user.id, body.filename)
    r2_upload_id = storage.create_multipart_upload(key, body.content_type)

    upload = Upload(
        user_id=user.id,
        r2_key=key,
        r2_upload_id=r2_upload_id,
        filename=body.filename,
        content_type=body.content_type,
        status=UploadStatus.in_progress,
        total_size=body.total_size,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.upload_expire_hours),
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    return UploadCreateResponse(upload_id=upload.id, part_size=settings.upload_part_size)


def _get_upload_or_404(db: Session, user: User, upload_id: uuid.UUID) -> Upload:
    upload = db.get(Upload, upload_id)
    if upload is None or upload.user_id != user.id:
        raise not_found("upload")
    return upload


@router.post("/{upload_id}/parts", response_model=UploadPartsResponse)
def get_part_urls(
    upload_id: uuid.UUID,
    body: UploadPartsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadPartsResponse:
    upload = _get_upload_or_404(db, user, upload_id)
    urls = {
        part_number: storage.presign_part_url(upload.r2_key, upload.r2_upload_id, part_number)
        for part_number in body.part_numbers
    }
    return UploadPartsResponse(urls=urls)


@router.get("/{upload_id}", response_model=UploadStatusResponse)
def get_upload_status(
    upload_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UploadStatusResponse:
    upload = _get_upload_or_404(db, user, upload_id)
    completed_parts: list[dict] = []
    if upload.status == UploadStatus.in_progress:
        parts = storage.list_parts(upload.r2_key, upload.r2_upload_id)
        completed_parts = [{"part_number": p["part_number"]} for p in parts]
    return UploadStatusResponse(status=upload.status.value, completed_parts=completed_parts)


@router.post("/{upload_id}/complete", status_code=204)
def complete_upload(
    upload_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    upload = _get_upload_or_404(db, user, upload_id)
    storage.complete_multipart_upload(upload.r2_key, upload.r2_upload_id)
    upload.status = UploadStatus.completed
    db.commit()


@router.delete("/{upload_id}", status_code=204)
def abort_upload(
    upload_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    upload = _get_upload_or_404(db, user, upload_id)
    storage.abort_multipart_upload(upload.r2_key, upload.r2_upload_id)
    upload.status = UploadStatus.aborted
    db.commit()
