"""キーフレーム検出（外側スナップの基礎。02 §動画編集パイプライン）。"""

import subprocess


def list_keyframe_timestamps(path: str) -> list[float]:
    # フィールド名は `pts_time`（`pkt_pts_time` は新しいffmpegで廃止されており
    # 黙って空リストを返すため、実機検証で気づきにくいバグになりやすい）。
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v",
        "-skip_frame",
        "nokey",
        "-show_entries",
        "frame=pts_time",
        "-of",
        "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    timestamps = []
    for line in result.stdout.splitlines():
        # 先頭フレームにside_dataが付き列数が増えることがあるため、
        # 最初のフィールドだけを取る（実機検証で判明した末尾カンマの実例）。
        first_field = line.strip().split(",")[0]
        if first_field and first_field != "N/A":
            timestamps.append(float(first_field))
    return sorted(timestamps)


def snap_outside(start_s: float, end_s: float, keyframes: list[float], duration_s: float) -> tuple[float, float]:
    """区間を「外側に」拡張する — プレー区間を削らない方向（02: 不変原則を反映した編集方針）。"""
    snapped_start = 0.0
    for kf in keyframes:
        if kf <= start_s:
            snapped_start = kf
        else:
            break

    snapped_end = duration_s
    for kf in reversed(keyframes):
        if kf >= end_s:
            snapped_end = kf
        else:
            break

    return snapped_start, snapped_end


def merge_overlapping(segments: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """スナップ後に重複・隣接した区間を結合する（クリップ重複防止。10のRound2指摘への対応）。"""
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: s[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]
