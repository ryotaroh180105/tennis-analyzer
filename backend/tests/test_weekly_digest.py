"""週次ダイジェスト選定ロジックのテスト（実DBに対して実行。conftest._clean_dbが後始末する）。"""

from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.models.match import EventStream, Match, MatchStatus
from app.models.advice import AdviceDelivery, AdviceDeliveryKind
from app.models.user import User
from app.services.weekly_digest import select_weekly_notifications


def _make_user(db):
    user = User(display_name="Test User", email="test@example.com", locale="ja")
    db.add(user)
    db.flush()
    return user


def _payload(points):
    return {"points": points}


def _forehand_point(index, outcome="net", pressure_hint="unforced"):
    # taxonomy_engineのpressure判定はwhen式依存のため、ここではnet終端(unforced寄り)を使う
    return {
        "index": index,
        "clip": {"start_s": float(index) * 5, "end_s": float(index) * 5 + 4},
        "shot_count": 2,
        "shots": [
            {"index": 0, "type": "serve", "type_confidence": 1.0},
            {"index": 1, "type": "forehand", "type_confidence": 0.9, "terminal": {"type": outcome, "confidence": 0.9}},
        ],
    }


def _serve_fault_point(index):
    return {
        "index": index,
        "clip": {"start_s": float(index) * 5, "end_s": float(index) * 5 + 4},
        "shot_count": 1,
        "shots": [{"index": 0, "type": "serve", "type_confidence": 1.0, "terminal": {"type": "net", "confidence": 0.9}}],
    }


def _serve_ok_point(index):
    return {
        "index": index,
        "clip": {"start_s": float(index) * 5, "end_s": float(index) * 5 + 4},
        "shot_count": 2,
        "shots": [
            {"index": 0, "type": "serve", "type_confidence": 1.0},
            {"index": 1, "type": "forehand", "type_confidence": 0.9, "terminal": {"type": "winner", "confidence": 0.9}},
        ],
    }


def _add_match(db, user, points):
    match = Match(user_id=user.id, upload_id=_dummy_upload_id(db, user), title="t", status=MatchStatus.done)
    db.add(match)
    db.flush()
    db.add(EventStream(match_id=match.id, version=1, payload=_payload(points)))
    db.flush()
    return match


def _dummy_upload_id(db, user):
    from app.models.upload import Upload, UploadStatus

    upload = Upload(
        user_id=user.id,
        r2_key="dummy",
        r2_upload_id="dummy",
        filename="dummy.mp4",
        content_type="video/mp4",
        status=UploadStatus.completed,
        total_size=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(upload)
    db.flush()
    return upload.id


def test_no_matches_returns_none():
    db = SessionLocal()
    try:
        user = _make_user(db)
        db.commit()
        assert select_weekly_notifications(db, user.id) is None
    finally:
        db.close()


def test_serve_fault_spike_selected_when_no_prior_delivery():
    db = SessionLocal()
    try:
        user = _make_user(db)
        # 直近5試合の平均サーブミス率を低く保ち、最新試合だけ急増させる
        for _ in range(4):
            _add_match(db, user, [_serve_ok_point(0), _serve_ok_point(1), _serve_ok_point(2), _serve_ok_point(3)])
        _add_match(
            db,
            user,
            [_serve_fault_point(i) for i in range(9)] + [_serve_ok_point(9)],
        )
        db.commit()

        result = select_weekly_notifications(db, user.id)
        assert result is not None
        assert result["trigger"] is not None
        assert result["trigger"]["id"] == "serve_fault_spike"
    finally:
        db.close()


def test_trigger_respects_cooldown():
    db = SessionLocal()
    try:
        user = _make_user(db)
        for _ in range(4):
            _add_match(db, user, [_serve_ok_point(0), _serve_ok_point(1)])
        _add_match(db, user, [_serve_fault_point(i) for i in range(9)] + [_serve_ok_point(9)])
        db.commit()

        # 3日前に同じトリガーが配信済み → cooldown_days=7未満なので今回は選ばれない
        db.add(
            AdviceDelivery(
                user_id=user.id,
                kind=AdviceDeliveryKind.trigger,
                trigger_id="serve_fault_spike",
                content={},
                metrics_snapshot={"serve_fault_rate": 0.5},
                created_at=datetime.now(timezone.utc) - timedelta(days=3),
            )
        )
        db.commit()

        result = select_weekly_notifications(db, user.id)
        assert result["trigger"] is None
    finally:
        db.close()


def test_weekly_cap_blocks_second_trigger_even_if_cooldown_ok():
    db = SessionLocal()
    try:
        user = _make_user(db)
        for _ in range(4):
            _add_match(db, user, [_serve_ok_point(0), _serve_ok_point(1)])
        _add_match(db, user, [_serve_fault_point(i) for i in range(9)] + [_serve_ok_point(9)])
        db.commit()

        # 別トリガーが今週すでに1件配信済み（max_trigger_notifications_per_week=1）
        db.add(
            AdviceDelivery(
                user_id=user.id,
                kind=AdviceDeliveryKind.trigger,
                trigger_id="backhand_unforced_trend",
                content={},
                metrics_snapshot={},
                created_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        db.commit()

        result = select_weekly_notifications(db, user.id)
        assert result["trigger"] is None
    finally:
        db.close()


def test_improved_since_last_advice_marks_praise_fired():
    db = SessionLocal()
    try:
        user = _make_user(db)
        _add_match(db, user, [_serve_ok_point(0), _serve_ok_point(1)])
        db.commit()

        # 前回serve_fault_spikeを配信した時点のスナップショットは高い値 → 今回は下がっている想定
        db.add(
            AdviceDelivery(
                user_id=user.id,
                kind=AdviceDeliveryKind.trigger,
                trigger_id="serve_fault_spike",
                content={},
                metrics_snapshot={"serve_fault_rate": 0.9},
                created_at=datetime.now(timezone.utc) - timedelta(days=10),
            )
        )
        db.commit()

        result = select_weekly_notifications(db, user.id)
        assert result is not None
        assert result["praise_fired"] is True
    finally:
        db.close()
