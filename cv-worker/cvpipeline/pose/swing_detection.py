"""スイング自動分割（12-form-analysis.md §1動画=複数スイング前提）。

利き手首のワールド座標速度のピークをスイング候補とみなし、前後窓を切り出す。
ピーク検出の閾値・窓幅は shot-mechanics.v1.yaml の swing_detection セクションで
外出しする（不変原則2）。
"""

import math


def _wrist_speeds(landmark_series: list[dict], dominant_side: str) -> list[tuple[float, float, int]]:
    """(t, speed_m_per_s, index) のリスト。速度は有効フレーム間の直線距離/経過時間。"""
    valid_indices = [i for i, f in enumerate(landmark_series) if f["joints"] is not None]
    speeds = []
    for k in range(1, len(valid_indices)):
        i0, i1 = valid_indices[k - 1], valid_indices[k]
        f0, f1 = landmark_series[i0], landmark_series[i1]
        dt = f1["t"] - f0["t"]
        if dt <= 0:
            continue
        w0 = f0["joints"][f"{dominant_side}_wrist"]
        w1 = f1["joints"][f"{dominant_side}_wrist"]
        dist = math.sqrt((w1["x"] - w0["x"]) ** 2 + (w1["y"] - w0["y"]) ** 2 + (w1["z"] - w0["z"]) ** 2)
        speeds.append((f1["t"], dist / dt, i1))
    return speeds


def detect_swing_peaks(landmark_series: list[dict], dominant_side: str, config: dict) -> list[tuple[float, float]]:
    """(peak_t, peak_speed) のリストをt昇順で返す。min_interval_s未満で連続するピークは
    速度が大きい方だけを残す（同一スイングの重複検出を防ぐ）。"""
    speeds = _wrist_speeds(landmark_series, dominant_side)
    min_peak = config["min_peak_speed_mps"]
    min_interval = config["min_interval_s"]

    peaks: list[list[float]] = []
    for t, speed, _idx in speeds:
        if speed < min_peak:
            continue
        if peaks and t - peaks[-1][0] < min_interval:
            if speed > peaks[-1][1]:
                peaks[-1] = [t, speed]
            continue
        peaks.append([t, speed])

    return [(t, speed) for t, speed in peaks]


def split_swings(landmark_series: list[dict], dominant_side: str, config: dict) -> list[list[dict]]:
    """スイングごとのランドマークウィンドウのリストを返す（ピークが無ければ空リスト）。"""
    peaks = detect_swing_peaks(landmark_series, dominant_side, config)
    pre_s, post_s = config["window_pre_s"], config["window_post_s"]

    windows = []
    for peak_t, _speed in peaks:
        window = [f for f in landmark_series if (peak_t - pre_s) <= f["t"] <= (peak_t + post_s)]
        if window:
            windows.append(window)
    return windows
