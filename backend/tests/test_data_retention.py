"""データライフサイクル保持バッチのテスト（08 §データライフサイクル・プライバシー、
設計レビュー13 E'）。"""

import datetime as dt
import uuid

import pytest

from app.core.db import SessionLocal
from app.jobs import tasks as tasks_module
from app.jobs.tasks import run_data_retention
from app.models.match import Match, MatchStatus, VideoAsset, VideoAssetKind
from app.models.upload import Upload, UploadStatus
from app.models.user import User
from app.services import storage


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def _make_user(db) -> User:
    user = User(display_name="Retention Test User", locale="ja")
    db.add(user)
    db.commit()
    return user


def _make_match(db, user: User) -> Match:
    upload = Upload(
        user_id=user.id,
        r2_key=f"uploads/{uuid.uuid4()}.mp4",
        r2_upload_id="fake",
        filename="test.mp4",
        content_type="video/mp4",
        status=UploadStatus.completed,
        total_size=1024,
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=48),
    )
    db.add(upload)
    db.commit()

    match = Match(user_id=user.id, upload_id=upload.id, title="Retention Test Match", status=MatchStatus.done)
    db.add(match)
    db.commit()
    return match


def _make_asset(db, match: Match, kind: VideoAssetKind, age_days: int, key: str) -> VideoAsset:
    storage.put_object_bytes(key, b"fake-video-bytes", content_type="video/mp4")
    asset = VideoAsset(match_id=match.id, kind=kind, generation=0, r2_key=key)
    db.add(asset)
    db.commit()
    asset.created_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=age_days)
    db.commit()
    return asset


def test_asset_past_retention_is_deleted_from_db_and_s3(client, db):
    user = _make_user(db)
    match = _make_match(db, user)
    key = f"matches/{match.id}/original.mp4"
    asset = _make_asset(db, match, VideoAssetKind.original, age_days=31, key=key)  # original: 30日
    asset_id = asset.id

    run_data_retention()

    db.expire_all()
    assert db.get(VideoAsset, asset_id) is None
    with pytest.raises(Exception):  # noqa: B017 — S3互換APIは削除済みキーのGETで例外
        storage.get_object_bytes(key)


def test_asset_within_retention_is_kept(client, db):
    user = _make_user(db)
    match = _make_match(db, user)
    key = f"matches/{match.id}/original.mp4"
    asset = _make_asset(db, match, VideoAssetKind.original, age_days=10, key=key)  # original: 30日、まだ猶予あり
    asset_id = asset.id

    run_data_retention()

    db.expire_all()
    assert db.get(VideoAsset, asset_id) is not None
    assert storage.get_object_bytes(key) == b"fake-video-bytes"  # S3側にも残っている


def test_hls_asset_deletion_removes_whole_prefix(client, db):
    user = _make_user(db)
    match = _make_match(db, user)
    prefix = f"matches/{match.id}/gen0/hls"
    playlist_key = f"{prefix}/playlist.m3u8"
    segment_key = f"{prefix}/seg0.ts"
    storage.put_object_bytes(segment_key, b"ts-bytes", content_type="video/mp2t")
    asset = _make_asset(db, match, VideoAssetKind.hls, age_days=91, key=playlist_key)  # hls: 90日
    asset_id = asset.id

    run_data_retention()

    db.expire_all()
    assert db.get(VideoAsset, asset_id) is None
    with pytest.raises(Exception):  # noqa: B017
        storage.get_object_bytes(segment_key)  # プレイリストだけでなくセグメントも削除される


def test_asset_at_notice_window_notifies_but_is_not_deleted(client, db, monkeypatch):
    notified = []
    monkeypatch.setattr(tasks_module, "notify_user", lambda user, message: notified.append((user.id, message)))

    user = _make_user(db)
    match = _make_match(db, user)
    key = f"matches/{match.id}/original.mp4"
    # original: 30日保持、通知は3日前 → age_days=27で残り3日
    asset = _make_asset(db, match, VideoAssetKind.original, age_days=27, key=key)
    asset_id = asset.id

    run_data_retention()

    db.expire_all()
    assert db.get(VideoAsset, asset_id) is not None  # まだ削除されない
    assert len(notified) == 1
    assert notified[0][0] == user.id
    assert "3日後に削除" in notified[0][1]
