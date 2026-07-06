"""アップロード〜試合作成〜区間取得のE2E疎通テスト（10 §API契約）。"""

import httpx


def test_upload_and_match_lifecycle(client):
    resp = client.post(
        "/api/uploads",
        json={"filename": "test.mp4", "total_size": 1024 * 1024, "content_type": "video/mp4"},
    )
    assert resp.status_code == 200
    upload_id = resp.json()["upload_id"]

    resp = client.post(f"/api/uploads/{upload_id}/parts", json={"part_numbers": [1]})
    assert resp.status_code == 200
    part_url = resp.json()["urls"]["1"]

    put_resp = httpx.put(part_url, content=b"FAKEDATA" * 1000)
    assert put_resp.status_code == 200

    resp = client.get(f"/api/uploads/{upload_id}")
    assert resp.json()["completed_parts"] == [{"part_number": 1}]

    resp = client.post(f"/api/uploads/{upload_id}/complete")
    assert resp.status_code == 204

    resp = client.post("/api/matches", json={"upload_id": upload_id, "title": "Test Match"})
    assert resp.status_code == 200
    match_id = resp.json()["id"]
    assert resp.json()["status"] == "queued"

    # 使用済みuploadでの再作成は409
    resp = client.post("/api/matches", json={"upload_id": upload_id, "title": "dup"})
    assert resp.status_code == 409

    resp = client.get("/api/matches")
    assert len(resp.json()) == 1

    resp = client.get(f"/api/matches/{match_id}")
    assert resp.status_code == 200
    assert resp.json()["progress"]["stage"] == "precheck"

    resp = client.get(f"/api/matches/{match_id}/segments")
    assert resp.status_code == 200
    assert resp.json() == {"revision": 0, "effective": [], "raw": []}


def test_match_not_found_returns_404(client):
    resp = client.get("/api/matches/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_upload_rejects_non_video_content_type(client):
    resp = client.post(
        "/api/uploads",
        json={"filename": "test.txt", "total_size": 100, "content_type": "text/plain"},
    )
    assert resp.status_code == 422


def test_upload_rejects_oversized_file(client):
    resp = client.post(
        "/api/uploads",
        json={"filename": "huge.mp4", "total_size": 999_999_999_999, "content_type": "video/mp4"},
    )
    assert resp.status_code == 413
