"""ゴールデンセット回帰（10 §ゴールデンセット。08の品質ゲート）。

golden/labels/{id}.json の正解区間と、stage1-4パイプラインの出力を比較する。
合否判定：正解区間とのIoU >= 0.8（境界許容±1.0s）を一致とし、
precision >= 0.90 かつ recall >= 0.80 を下回ったらfail。
"""

import json
import sys
from pathlib import Path

from cvpipeline.pipeline import run_analyze

GOLDEN_DIR = Path("/app/golden")
LABELS_DIR = GOLDEN_DIR / "labels"
VIDEOS_DIR = GOLDEN_DIR / "videos"  # .gitignore対象。実動画は別途配置する


def is_match(pred: dict, gt: dict) -> bool:
    if abs(pred["start_s"] - gt["start_s"]) <= 1.0 and abs(pred["end_s"] - gt["end_s"]) <= 1.0:
        return True
    return _iou(pred, gt) >= 0.8


def _iou(a: dict, b: dict) -> float:
    inter_start = max(a["start_s"], b["start_s"])
    inter_end = min(a["end_s"], b["end_s"])
    inter = max(0.0, inter_end - inter_start)
    union = (a["end_s"] - a["start_s"]) + (b["end_s"] - b["start_s"]) - inter
    return inter / union if union > 0 else 0.0


def evaluate(pred_segments: list[dict], gt_segments: list[dict]) -> dict:
    matched_gt = set()
    matched_pred = 0
    for p in sorted(pred_segments, key=lambda s: -max((_iou(s, g) for g in gt_segments), default=0)):
        best_gt_idx = None
        best_iou = 0.0
        for i, g in enumerate(gt_segments):
            if i in matched_gt:
                continue
            if is_match(p, g):
                iou = _iou(p, g)
                if iou > best_iou:
                    best_iou = iou
                    best_gt_idx = i
        if best_gt_idx is not None:
            matched_gt.add(best_gt_idx)
            matched_pred += 1

    precision = matched_pred / len(pred_segments) if pred_segments else 0.0
    recall = len(matched_gt) / len(gt_segments) if gt_segments else 0.0
    return {"precision": precision, "recall": recall, "matched": matched_pred, "total_pred": len(pred_segments), "total_gt": len(gt_segments)}


def main() -> int:
    if not LABELS_DIR.exists():
        print(f"no golden labels found at {LABELS_DIR}")
        return 0

    label_files = sorted(LABELS_DIR.glob("*.json"))
    if not label_files:
        print("no golden label files found — nothing to evaluate yet (acquire per 10 §ゴールデンセット M1タスク)")
        return 0

    overall_fail = False
    for label_path in label_files:
        video_id = label_path.stem
        video_path = VIDEOS_DIR / f"{video_id}.mp4"
        if not video_path.exists():
            print(f"[SKIP] {video_id}: video file not found at {video_path}")
            continue

        gt = json.loads(label_path.read_text())["segments"]
        result = run_analyze(str(video_path), degraded=False)
        pred = result["segments"]

        metrics = evaluate(pred, gt)
        status = "PASS" if metrics["precision"] >= 0.90 and metrics["recall"] >= 0.80 else "FAIL"
        if status == "FAIL":
            overall_fail = True
        print(f"[{status}] {video_id}: precision={metrics['precision']:.2f} recall={metrics['recall']:.2f}")

    return 1 if overall_fail else 0


if __name__ == "__main__":
    sys.exit(main())
