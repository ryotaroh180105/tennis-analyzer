"""ステージ2: 選手（人物）活動量（02/10）。

Phase 0の割り切り：選手同定・個別トラッキングは不要で「コート内の活動量」が
取れれば十分（10 §CVパイプライン Phase 0 実装指針）。
YOLO系検出器の導入はUltralytics(AGPL)のライセンス確認待ち（05 §CV）のため、
このdev実装は背景差分ベースの古典的CVで代替する（dev軽量モードの定義：
精度非保証・パイプライン疎通が目的。10 §リポジトリ構成）。
本番相当の精度が必要になった時点でRT-DETR/YOLOX等（Apache-2.0系）に差し替える。
"""

import cv2
import numpy as np

from cvpipeline.config_loader import load_segmentation_params


def _court_mask(frame_shape, court_polygon_px, degraded: bool) -> np.ndarray:
    h, w = frame_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    if degraded or court_polygon_px is None:
        params = load_segmentation_params()["degraded"]
        x1, y1, x2, y2 = params["center_roi"]
        cv2.rectangle(mask, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), 255, -1)
    else:
        pts = np.array(court_polygon_px, dtype=np.int32)
        cv2.fillConvexPoly(mask, pts, 255)
    return mask


def analyze_person_motion(
    video_path: str, court_polygon_px, hz: float, max_seconds: float | None, degraded: bool
) -> dict:
    from cvpipeline.video_io import sample_frames

    back_sub = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=32, detectShadows=False)
    mask_cache = None
    per_frame = []
    frame_count = 0

    for t, frame in sample_frames(video_path, hz=hz, max_seconds=max_seconds):
        if mask_cache is None:
            mask_cache = _court_mask(frame.shape, court_polygon_px, degraded)

        fg = back_sub.apply(frame)
        fg = cv2.bitwise_and(fg, fg, mask=mask_cache)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))

        contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = frame.shape[0] * frame.shape[1] * 0.002
        blobs = [c for c in contours if cv2.contourArea(c) > min_area]

        court_area = float(mask_cache.sum()) / 255.0 or 1.0
        motion_energy = min(1.0, sum(cv2.contourArea(c) for c in blobs) / court_area)

        per_frame.append({"t": round(t, 2), "n_persons": len(blobs), "person_motion": round(motion_energy, 4)})
        frame_count += 1

    confidence = 0.85 if frame_count > 0 else 0.0
    return {"hz": hz, "per_frame": per_frame, "confidence": confidence}
