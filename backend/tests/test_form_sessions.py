"""フォーム解析セッションAPIのE2E疎通テスト（Phase 3拡張。12-form-analysis.md）。"""

import httpx


def _completed_upload(client) -> str:
    resp = client.post(
        "/api/uploads",
        json={"filename": "forehand.mp4", "total_size": 1024 * 1024, "content_type": "video/mp4"},
    )
    upload_id = resp.json()["upload_id"]
    resp = client.post(f"/api/uploads/{upload_id}/parts", json={"part_numbers": [1]})
    part_url = resp.json()["urls"]["1"]
    httpx.put(part_url, content=b"FAKEDATA" * 1000)
    client.post(f"/api/uploads/{upload_id}/complete")
    return upload_id


def test_form_session_lifecycle(client):
    upload_id = _completed_upload(client)

    resp = client.post(
        "/api/form-sessions", json={"upload_id": upload_id, "title": "フォアハンド練習1", "shot_type": "forehand"}
    )
    assert resp.status_code == 200
    body = resp.json()
    session_id = body["id"]
    assert body["status"] == "queued"
    assert body["shot_type"] == "forehand"
    assert body["backhand_style"] is None

    # 使用済みuploadでの再作成は409（matchesと同じ流用ルール）
    resp = client.post(
        "/api/form-sessions", json={"upload_id": upload_id, "title": "dup", "shot_type": "forehand"}
    )
    assert resp.status_code == 409

    resp = client.get("/api/form-sessions")
    assert len(resp.json()) == 1

    resp = client.get(f"/api/form-sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "フォアハンド練習1"

    # 解析未完了（run_form_analyzeを実際には起動していない）のためanalysisは404
    resp = client.get(f"/api/form-sessions/{session_id}/analysis")
    assert resp.status_code == 404


def test_form_session_backhand_style_is_persisted(client):
    upload_id = _completed_upload(client)
    resp = client.post(
        "/api/form-sessions",
        json={
            "upload_id": upload_id,
            "title": "両手バック練習",
            "shot_type": "backhand",
            "backhand_style": "two_handed",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["backhand_style"] == "two_handed"


def test_form_session_rejects_unknown_shot_type(client):
    upload_id = _completed_upload(client)
    resp = client.post(
        "/api/form-sessions", json={"upload_id": upload_id, "title": "x", "shot_type": "dropshot"}
    )
    assert resp.status_code == 422


def test_form_session_not_found_returns_404(client):
    resp = client.get("/api/form-sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_form_analysis_response_includes_per_swing_data(client):
    # 13 E'-swing-strip: FormAnalysisResponseはswingsを含む（フォーム解析詳細ページの
    # スイング一覧ストリップが個々のスイングの完全性・外れ値を可視化するために必要）
    from app.core.db import SessionLocal
    from app.models.form import FormAnalysis

    upload_id = _completed_upload(client)
    resp = client.post(
        "/api/form-sessions", json={"upload_id": upload_id, "title": "スイング確認", "shot_type": "forehand"}
    )
    session_id = resp.json()["id"]

    payload = {
        "shot_type": "forehand",
        "dominant_side": "right",
        "swing_count": 2,
        "insufficient_data": False,
        "swings": [
            {
                "t": 1.2,
                "metrics": {
                    "elbow_angle_at_contact": {"id": "elbow_angle_at_contact", "value": 120.0, "confidence": 0.9}
                },
            },
            {
                "t": 5.6,
                "metrics": {
                    "elbow_angle_at_contact": {"id": "elbow_angle_at_contact", "value": None, "confidence": 0.0}
                },
            },
        ],
        "metrics": [],
        "feedback_metrics": [],
        "confidence": {"pose_detection_ratio": 0.8},
        "citation_status": "placeholder_pending_literature_review",
    }

    db = SessionLocal()
    db.add(FormAnalysis(form_session_id=session_id, payload=payload))
    db.commit()
    db.close()

    resp = client.get(f"/api/form-sessions/{session_id}/analysis")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["swings"]) == 2
    assert body["swings"][0]["t"] == 1.2
    assert body["swings"][0]["metrics"]["elbow_angle_at_contact"]["value"] == 120.0
    assert body["swings"][1]["metrics"]["elbow_angle_at_contact"]["value"] is None
