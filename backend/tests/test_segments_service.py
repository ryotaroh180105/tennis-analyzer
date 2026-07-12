"""区間の有効区間計算ロジック（純粋関数）のユニットテスト。10 §segments。"""

import uuid
from datetime import datetime, timezone

import pytest

from app.core.errors import ApiError
from app.models.segment import Segment, SegmentOp, SegmentSource
from app.services import segments as segments_service


def _make_segment(revision, op, start_s=None, end_s=None, base_segment_id=None, seg_id=None, confidence=None):
    seg = Segment(
        id=seg_id or uuid.uuid4(),
        match_id=uuid.uuid4(),
        revision=revision,
        op=op,
        base_segment_id=base_segment_id,
        start_s=start_s,
        end_s=end_s,
        source=SegmentSource.auto if revision == 0 else SegmentSource.user,
        confidence=confidence,
    )
    seg.created_at = datetime.now(timezone.utc)
    return seg


def test_compute_effective_with_only_auto_segments():
    rows = [
        _make_segment(0, SegmentOp.add, 5.0, 10.0),
        _make_segment(0, SegmentOp.add, 20.0, 30.0),
    ]
    effective = segments_service.compute_effective(rows)
    assert effective == [
        {"start_s": 5.0, "end_s": 10.0, "confidence": None},
        {"start_s": 20.0, "end_s": 30.0, "confidence": None},
    ]


def test_compute_effective_remove_op():
    auto1 = _make_segment(0, SegmentOp.add, 5.0, 10.0)
    auto2 = _make_segment(0, SegmentOp.add, 20.0, 30.0)
    remove = _make_segment(1, SegmentOp.remove, base_segment_id=auto1.id)
    effective = segments_service.compute_effective([auto1, auto2, remove])
    assert effective == [{"start_s": 20.0, "end_s": 30.0, "confidence": None}]


def test_compute_effective_adjust_op():
    auto1 = _make_segment(0, SegmentOp.add, 5.0, 10.0)
    adjust = _make_segment(1, SegmentOp.adjust, 4.0, 11.0, base_segment_id=auto1.id)
    effective = segments_service.compute_effective([auto1, adjust])
    assert effective == [{"start_s": 4.0, "end_s": 11.0, "confidence": None}]


def test_compute_effective_user_add_then_remove():
    """ユーザーが自分で追加した区間を、後続の操作で削除できる（base_segment_idがuser add行を指す）。"""
    user_add = _make_segment(1, SegmentOp.add, 40.0, 50.0)
    remove = _make_segment(2, SegmentOp.remove, base_segment_id=user_add.id)
    effective = segments_service.compute_effective([user_add, remove])
    assert effective == []


def test_compute_effective_carries_confidence_from_auto_add():
    # 13 B-2: CV自動検出の信頼度がeffectiveまで伝播し、低信頼リボン表示に使われる
    rows = [_make_segment(0, SegmentOp.add, 5.0, 10.0, confidence=0.6)]
    effective = segments_service.compute_effective(rows)
    assert effective == [{"start_s": 5.0, "end_s": 10.0, "confidence": 0.6}]


def test_compute_effective_adjust_clears_confidence():
    # ユーザーが境界を直接修正した時点でCV固有の「低信頼」シグナルは意味を失う（不変原則1）
    auto1 = _make_segment(0, SegmentOp.add, 5.0, 10.0, confidence=0.6)
    adjust = _make_segment(1, SegmentOp.adjust, 4.0, 11.0, base_segment_id=auto1.id)
    effective = segments_service.compute_effective([auto1, adjust])
    assert effective == [{"start_s": 4.0, "end_s": 11.0, "confidence": None}]


def test_current_revision():
    rows = [_make_segment(0, SegmentOp.add, 5.0, 10.0), _make_segment(3, SegmentOp.remove)]
    assert segments_service.current_revision(rows) == 3
    assert segments_service.current_revision([]) == 0


def test_validate_op_rejects_start_after_end():
    with pytest.raises(ApiError):
        segments_service.validate_op("add", 10.0, 5.0, None, 100.0)


def test_validate_op_rejects_end_beyond_duration():
    with pytest.raises(ApiError):
        segments_service.validate_op("add", 5.0, 200.0, None, 100.0)


def test_validate_op_remove_requires_base_id():
    with pytest.raises(ApiError):
        segments_service.validate_op("remove", None, None, None, 100.0)


def test_validate_op_accepts_valid_add():
    segments_service.validate_op("add", 5.0, 10.0, None, 100.0)  # 例外を投げなければOK
