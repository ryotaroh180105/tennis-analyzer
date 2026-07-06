"""ステージ1: コート検出（白線検出＋ホモグラフィ推定、02/05/10）。

自前の薄い実装：白線を色閾値+Hough変換で検出し、外周4隅（ダブルスサイドライン×
両ベースライン）を推定してcourt-spec.v1.yamlのコート座標系へのホモグラフィを求める。
学習ベース検出ではなく古典的CVのため、オムニコート等コントラストの低い環境では
confidenceが下がる想定（縮退モードで受ける。03/10）。
"""

import cv2
import numpy as np

from cvpipeline.config_loader import load_court_spec


def _detect_white_line_mask(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # 白線は「明るく彩度が低い」領域。HSVでVが高くSが低い画素を抽出する方がコート地の色に
    # ロバスト（オムニの緑・ハードの青系どちらでも白線は相対的に明るい）。
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    _, sat, val = cv2.split(hsv)
    mask = cv2.inRange(sat, 0, 60) & cv2.inRange(val, 170, 255)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return mask


def _find_court_lines(mask: np.ndarray) -> list[tuple[float, float, float, float]]:
    lines = cv2.HoughLinesP(
        mask, rho=1, theta=np.pi / 180, threshold=80, minLineLength=mask.shape[1] // 6, maxLineGap=20
    )
    if lines is None:
        return []
    # cv2.HoughLinesP は環境により (N,1,4) と (N,4) のどちらの形状でも返り得るため
    # reshape で吸収する（実機検証で判明）。
    flat = np.asarray(lines).reshape(-1, 4)
    return [tuple(map(float, line)) for line in flat]


def _classify_lines(lines: list[tuple[float, float, float, float]]):
    horizontal, vertical = [], []
    for x1, y1, x2, y2 in lines:
        angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if angle < 20 or angle > 160:
            horizontal.append((x1, y1, x2, y2))
        elif 70 < angle < 110:
            vertical.append((x1, y1, x2, y2))
    return horizontal, vertical


def _extreme_corners(horizontal, vertical, frame_shape) -> np.ndarray | None:
    """検出した水平線・垂直線の交点から外周4隅を推定する簡易ロジック。"""
    if len(horizontal) < 2 or len(vertical) < 2:
        return None

    h, w = frame_shape[:2]

    def line_y_at(line, x):
        x1, y1, x2, y2 = line
        if x2 == x1:
            return (y1 + y2) / 2
        t = (x - x1) / (x2 - x1)
        return y1 + t * (y2 - y1)

    top_line = min(horizontal, key=lambda l: (l[1] + l[3]) / 2)
    bottom_line = max(horizontal, key=lambda l: (l[1] + l[3]) / 2)
    left_line = min(vertical, key=lambda l: (l[0] + l[2]) / 2)
    right_line = max(vertical, key=lambda l: (l[0] + l[2]) / 2)

    left_x = (left_line[0] + left_line[2]) / 2
    right_x = (right_line[0] + right_line[2]) / 2

    corners = np.array(
        [
            [left_x, line_y_at(top_line, left_x)],
            [right_x, line_y_at(top_line, right_x)],
            [right_x, line_y_at(bottom_line, right_x)],
            [left_x, line_y_at(bottom_line, left_x)],
        ],
        dtype=np.float32,
    )

    # 画面内に収まっているかの粗いサニティチェック
    if np.any(corners[:, 0] < -w * 0.2) or np.any(corners[:, 0] > w * 1.2):
        return None
    return corners


def detect_court(video_path: str, sample_seconds: float = 3.0) -> dict:
    """先頭sample_seconds分をサンプリングし、最も安定した検出を採用する。"""
    from cvpipeline.video_io import sample_frames

    spec = load_court_spec()
    court_w = spec["court"]["width_doubles"]
    court_l = spec["court"]["length"]
    # court-spec原点はネット中央。外周4隅（doubles sideline x baseline）をコート座標で表す
    dst_corners = np.array(
        [
            [-court_w / 2, court_l / 2],
            [court_w / 2, court_l / 2],
            [court_w / 2, -court_l / 2],
            [-court_w / 2, -court_l / 2],
        ],
        dtype=np.float32,
    )

    best: dict | None = None
    for _t, frame in sample_frames(video_path, hz=1.0, max_seconds=sample_seconds):
        mask = _detect_white_line_mask(frame)
        lines = _find_court_lines(mask)
        horizontal, vertical = _classify_lines(lines)
        corners_px = _extreme_corners(horizontal, vertical, frame.shape)
        if corners_px is None:
            continue

        homography, inliers = cv2.findHomography(corners_px, dst_corners, cv2.RANSAC, 5.0)
        if homography is None:
            continue

        inlier_ratio = float(inliers.sum()) / len(inliers) if inliers is not None else 0.0
        # 白線マスクの画素密度も信頼度に効かせる（検出が薄いほど怪しい）
        line_density = float(mask.mean()) / 255.0
        confidence = min(1.0, 0.5 * inlier_ratio + 0.5 * min(line_density * 20, 1.0))

        if best is None or confidence > best["confidence"]:
            best = {
                "court_detected": True,
                "homography": homography.tolist(),
                "court_polygon_px": corners_px.tolist(),
                "court_type": "unknown",  # Phase 0では種別分類はしない（10）
                "confidence": confidence,
                "spec_version": "court-spec.v1",
            }

    if best is None:
        return {
            "court_detected": False,
            "homography": None,
            "court_polygon_px": None,
            "court_type": "unknown",
            "confidence": 0.0,
            "spec_version": "court-spec.v1",
        }
    return best
