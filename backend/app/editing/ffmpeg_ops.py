"""FFmpeg編集（カット連結・HLS生成・サムネイル）。02 §動画編集パイプライン。

正規化済みH.264（GOP 2秒）に対して `-c copy` でカット・連結する
（再エンコードなし。GOP規定がこの精度を支える。02 Round2修正）。
"""

import subprocess
import tempfile
from pathlib import Path

from app.editing.keyframes import list_keyframe_timestamps, merge_overlapping, snap_outside
from app.core.config import get_settings


def build_edited_video(
    normalized_path: str, effective_segments: list[dict], duration_s: float, output_path: str
) -> None:
    keyframes = list_keyframe_timestamps(normalized_path)

    snapped = [
        snap_outside(seg["start_s"], seg["end_s"], keyframes, duration_s) for seg in effective_segments
    ]
    merged = merge_overlapping(snapped)

    if not merged:
        raise ValueError("no effective segments to cut")

    with tempfile.TemporaryDirectory() as tmpdir:
        clip_paths = []
        for i, (start, end) in enumerate(merged):
            clip_path = str(Path(tmpdir) / f"clip_{i:04d}.mp4")
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-to", str(end),
                "-i", normalized_path,
                "-c", "copy",
                clip_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            clip_paths.append(clip_path)

        filelist_path = str(Path(tmpdir) / "filelist.txt")
        with open(filelist_path, "w", encoding="utf-8") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", filelist_path,
            "-c", "copy",
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)


def build_hls(edited_path: str, output_dir: str) -> str:
    """単一レンディション・6秒セグメント、オーバーレイなし（10）。playlist.m3u8のパスを返す。"""
    settings = get_settings()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    playlist_path = str(Path(output_dir) / "playlist.m3u8")
    cmd = [
        "ffmpeg", "-y",
        "-i", edited_path,
        "-c", "copy",
        "-f", "hls",
        "-hls_time", str(settings.hls_segment_seconds),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(Path(output_dir) / "seg_%03d.ts"),
        playlist_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return playlist_path


def build_thumbnail(edited_path: str, output_path: str, at_seconds: float = 1.0) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(at_seconds),
        "-i", edited_path,
        "-vframes", "1",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
