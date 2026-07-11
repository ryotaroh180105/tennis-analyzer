"""サーブ骨格解析セッションAPIのE2E疎通テスト（Phase 3。01 §Phase3）。"""

import httpx


def _completed_upload(client) -> str:
    resp = client.post(
        "/api/uploads",
        json={"filename": "serve.mp4", "total_size": 1024 * 1024, "content_type": "video/mp4"},
    )
    upload_id = resp.json()["upload_id"]
    resp = client.post(f"/api/uploads/{upload_id}/parts", json={"part_numbers": [1]})
    part_url = resp.json()["urls"]["1"]
    httpx.put(part_url, content=b"FAKEDATA" * 1000)
    client.post(f"/api/uploads/{upload_id}/complete")
    return upload_id


def test_serve_session_lifecycle(client):
    upload_id = _completed_upload(client)

    resp = client.post("/api/serve-sessions", json={"upload_id": upload_id, "title": "サーブ練習1"})
    assert resp.status_code == 200
    session_id = resp.json()["id"]
    assert resp.json()["status"] == "queued"

    # 使用済みuploadでの再作成は409（matchesと同じ流用ルール）
    resp = client.post("/api/serve-sessions", json={"upload_id": upload_id, "title": "dup"})
    assert resp.status_code == 409

    resp = client.get("/api/serve-sessions")
    assert len(resp.json()) == 1

    resp = client.get(f"/api/serve-sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "サーブ練習1"

    # 解析未完了（run_serve_analyzeを実際には起動していない）のためanalysisは404
    resp = client.get(f"/api/serve-sessions/{session_id}/analysis")
    assert resp.status_code == 404


def test_serve_session_not_found_returns_404(client):
    resp = client.get("/api/serve-sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
