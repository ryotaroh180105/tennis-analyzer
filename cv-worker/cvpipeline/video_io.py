"""動画I/Oの共通ヘルパー（ffprobe呼び出し・フレームサンプリング）。"""

import json
import subprocess


def ffprobe(path: str) -> dict:
    """メタデータ取得（解像度/fps/回転/コーデック/HDR/duration）。"""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    video_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video_stream is None:
        raise ValueError("no video stream found")

    rotation = 0
    for side_data in video_stream.get("side_data_list", []):
        if "rotation" in side_data:
            rotation = int(side_data["rotation"])

    fps_raw = video_stream.get("avg_frame_rate", "0/1")
    num, den = fps_raw.split("/")
    fps = float(num) / float(den) if float(den) != 0 else 0.0

    return {
        "duration_s": float(data["format"].get("duration", 0.0)),
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "fps": fps,
        "codec": video_stream.get("codec_name", "unknown"),
        "rotation": rotation,
        "is_hevc": video_stream.get("codec_name") in ("hevc", "h265"),
        "color_transfer": video_stream.get("color_transfer"),
        "is_hdr": video_stream.get("color_transfer") in ("smpte2084", "arib-std-b67"),
    }


def sample_frames(path: str, hz: float, max_seconds: float | None = None):
    """OpenCVでhz間隔にフレームをサンプリングするジェネレータ。(t, frame) を yield する。"""
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(native_fps / hz))
    frame_idx = 0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    max_frames = int(max_seconds * native_fps) if max_seconds else total_frames

    while True:
        ok, frame = cap.read()
        if not ok or frame_idx > max_frames:
            break
        if frame_idx % step == 0:
            t = frame_idx / native_fps
            yield t, frame
        frame_idx += 1

    cap.release()


def sample_burst(path: str, hz: float, burst_frames: int, max_seconds: float | None = None):
    """各サンプリング時点で隣接burst_frames枚をまとめて返す（TrackNet系の入力前提。segmentation.v1.yaml）。"""
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(native_fps / hz))
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    max_frames = int(max_seconds * native_fps) if max_seconds else total_frames

    buffer: list = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame_idx > max_frames:
            break
        buffer.append(frame)
        if len(buffer) > burst_frames:
            buffer.pop(0)
        if frame_idx % step == 0 and len(buffer) == burst_frames:
            t = frame_idx / native_fps
            yield t, list(buffer)
        frame_idx += 1

    cap.release()
