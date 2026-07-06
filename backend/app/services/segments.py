"""区間（segments）の有効区間計算と検証。

真実源はDBの追加専用ログ（Segmentモデル）。有効区間はrevision昇順に
全opを適用した結果として毎回計算する（10 §segments）。
"""

import uuid

from app.core.errors import validation_error
from app.models.segment import Segment, SegmentOp


def compute_effective(rows: list[Segment]) -> list[dict]:
    """revision, created_at 昇順に op を適用し、生きている区間を start_s 昇順で返す。"""
    entries: dict[uuid.UUID, dict] = {}
    ordered = sorted(rows, key=lambda r: (r.revision, r.created_at))
    for row in ordered:
        if row.op == SegmentOp.add:
            entries[row.id] = {"start_s": row.start_s, "end_s": row.end_s, "alive": True}
        elif row.op == SegmentOp.remove:
            if row.base_segment_id in entries:
                entries[row.base_segment_id]["alive"] = False
        elif row.op == SegmentOp.adjust:
            if row.base_segment_id in entries:
                entries[row.base_segment_id]["start_s"] = row.start_s
                entries[row.base_segment_id]["end_s"] = row.end_s

    effective = [
        {"start_s": e["start_s"], "end_s": e["end_s"]} for e in entries.values() if e["alive"]
    ]
    effective.sort(key=lambda s: s["start_s"])
    return effective


def current_revision(rows: list[Segment]) -> int:
    if not rows:
        return 0
    return max(r.revision for r in rows)


def validate_op(op: str, start_s: float | None, end_s: float | None, base_segment_id, duration_s: float | None) -> None:
    if op not in ("add", "remove", "adjust"):
        raise validation_error(f"invalid op: {op}")

    if op == "remove":
        if base_segment_id is None:
            raise validation_error("remove requires base_segment_id")
        return

    if op in ("add", "adjust"):
        if start_s is None or end_s is None:
            raise validation_error(f"{op} requires start_s and end_s")
        if op == "adjust" and base_segment_id is None:
            raise validation_error("adjust requires base_segment_id")
        if not (start_s < end_s):
            raise validation_error("start_s must be < end_s", {"start_s": start_s, "end_s": end_s})
        if start_s < 0:
            raise validation_error("start_s must be >= 0")
        if duration_s is not None and end_s > duration_s:
            raise validation_error(
                "end_s exceeds video duration", {"end_s": end_s, "duration_s": duration_s}
            )
