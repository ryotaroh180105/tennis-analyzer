"""共有視聴ページAPIのテスト（10 §API契約、設計レビュー13 E'-share-ribbon）。"""

import httpx

from app.core.db import SessionLocal
from app.models.segment import Segment, SegmentOp, SegmentSource


def _completed_match(client) -> str:
    resp = client.post(
        "/api/uploads",
        json={"filename": "match.mp4", "total_size": 1024 * 1024, "content_type": "video/mp4"},
    )
    upload_id = resp.json()["upload_id"]
    resp = client.post(f"/api/uploads/{upload_id}/parts", json={"part_numbers": [1]})
    part_url = resp.json()["urls"]["1"]
    httpx.put(part_url, content=b"FAKEDATA" * 1000)
    client.post(f"/api/uploads/{upload_id}/complete")
    resp = client.post("/api/matches", json={"upload_id": upload_id, "title": "共有テスト"})
    return resp.json()["id"]


def test_share_playback_includes_segments_for_ribbon(client):
    match_id = _completed_match(client)

    db = SessionLocal()
    db.add(
        Segment(
            match_id=match_id,
            revision=0,
            op=SegmentOp.add,
            base_segment_id=None,
            start_s=5.0,
            end_s=10.0,
            source=SegmentSource.auto,
            confidence=0.85,
        )
    )
    db.add(
        Segment(
            match_id=match_id,
            revision=0,
            op=SegmentOp.add,
            base_segment_id=None,
            start_s=20.0,
            end_s=25.0,
            source=SegmentSource.auto,
            confidence=0.4,
        )
    )
    db.commit()
    db.close()

    resp = client.post(f"/api/matches/{match_id}/share")
    assert resp.status_code == 200
    share_url = resp.json()["url"]
    token = share_url.rsplit("/", 1)[-1]

    resp = client.get(f"/api/share/{token}/playback")
    assert resp.status_code == 200
    body = resp.json()
    assert body["segments"] == [
        {"start_s": 5.0, "end_s": 10.0, "confidence": 0.85},
        {"start_s": 20.0, "end_s": 25.0, "confidence": 0.4},
    ]


def test_share_playback_unknown_token_returns_404(client):
    resp = client.get("/api/share/does-not-exist/playback")
    assert resp.status_code == 404


def test_match_playback_does_not_include_share_only_segments_field(client):
    # matches.pyのplaybackはPlaybackResponseを共用するが、共有ページ専用のsegments
    # フィールドはこちらでは設定しない（Noneのまま）。回帰確認。
    match_id = _completed_match(client)
    resp = client.get(f"/api/matches/{match_id}/playback")
    assert resp.status_code == 200
    assert resp.json()["segments"] is None
