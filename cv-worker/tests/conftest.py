import os
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ.setdefault("CONFIG_DIR", str(Path(__file__).parent.parent.parent / "config"))


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory) -> str:
    """簡易合成テニスコート風動画（実CV検証用フィクスチャ）。

    緑地に白線の矩形コート＋周期的に動く2つの白丸（選手）と黄色の小さい丸（ボール）。
    6-12秒・15-20秒を「プレー中」、それ以外を「デッドタイム」として設計する。
    """
    out_dir = tmp_path_factory.mktemp("video")
    path = str(out_dir / "synthetic_match.mp4")

    w, h, fps, duration_s = 640, 360, 30, 20
    n_frames = fps * duration_s
    writer = cv2.VideoWriter(str(out_dir / "raw.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    margin_x, margin_y = 60, 40
    for i in range(n_frames):
        frame = np.full((h, w, 3), (60, 140, 60), dtype=np.uint8)
        cv2.rectangle(frame, (margin_x, margin_y), (w - margin_x, h - margin_y), (240, 240, 240), 3)
        cv2.line(frame, (margin_x, h // 2), (w - margin_x, h // 2), (240, 240, 240), 2)

        t = i / fps
        is_play = (6 <= t < 12) or (15 <= t < 20)
        if is_play:
            p1x = int(margin_x + 40 + (w - 2 * margin_x - 80) * (0.5 + 0.4 * np.sin(t * 1.5)))
            cv2.circle(frame, (p1x, h - margin_y - 30), 12, (255, 255, 255), -1)
            p2x = int(margin_x + 40 + (w - 2 * margin_x - 80) * (0.5 + 0.4 * np.sin(t * 1.7 + 1)))
            cv2.circle(frame, (p2x, margin_y + 30), 12, (255, 255, 255), -1)
            bx = int(margin_x + (w - 2 * margin_x) * (0.5 + 0.45 * np.sin(t * 6)))
            by = int(margin_y + (h - 2 * margin_y) * (0.5 + 0.45 * np.cos(t * 6)))
            cv2.circle(frame, (bx, by), 4, (0, 220, 255), -1)
        else:
            cv2.circle(frame, (w // 2, h - margin_y - 30), 12, (255, 255, 255), -1)
            cv2.circle(frame, (w // 2, margin_y + 30), 12, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()

    # H.264へ変換（cvpipelineのffprobeベース処理はraw mp4v出力と相性が悪いため）
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(out_dir / "raw.mp4"), "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        check=True,
        capture_output=True,
    )
    return path
