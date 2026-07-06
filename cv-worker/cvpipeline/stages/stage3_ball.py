"""ステージ3: ボール活動量（02/10）。

TrackNet系は隣接フレーム入力が前提（config/segmentation.v1.yaml の
sampling.ball_burst_frames）。本dev実装はTrackNetの学習済み重み（ライセンス・
調達が別タスク、05 §CV）を使わず、バースト内フレーム差分で「小さく速く動く物体」
の動きエネルギーを近似する古典的CV代替。Phase 0の要求は「ボールが動いているか」の
シグナルのみで十分（10）。
"""

import cv2
import numpy as np

from cvpipeline.config_loader import load_segmentation_params


def analyze_ball_motion(video_path: str, hz: float, max_seconds: float | None) -> dict:
    from cvpipeline.video_io import sample_burst

    params = load_segmentation_params()["sampling"]
    burst_frames = params["ball_burst_frames"]

    per_frame = []
    frame_count = 0

    for t, burst in sample_burst(video_path, hz=hz, burst_frames=burst_frames, max_seconds=max_seconds):
        grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in burst]
        diff1 = cv2.absdiff(grays[0], grays[1])
        diff2 = cv2.absdiff(grays[1], grays[2])
        combined = cv2.bitwise_and(diff1, diff2)
        _, thresh = cv2.threshold(combined, 25, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = grays[0].shape
        frame_area = h * w
        # ボールは小さい（画面の0.05%未満程度）高速移動ブロブ、という粗いヒューリスティック
        small_fast_blobs = [
            c for c in contours if 0 < cv2.contourArea(c) < frame_area * 0.0015
        ]

        ball_motion = min(1.0, len(small_fast_blobs) / 3.0)
        per_frame.append({"t": round(t, 2), "ball_motion": round(ball_motion, 4)})
        frame_count += 1

    confidence = 0.6 if frame_count > 0 else 0.0
    return {"hz": hz, "per_frame": per_frame, "confidence": confidence}
