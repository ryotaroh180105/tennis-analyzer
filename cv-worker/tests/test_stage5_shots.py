"""ステージ5（ショット検出）のユニットテスト。ball_motionのピーク検出のみを検証する
純粋関数テスト（実動画不要、01 §Phase1）。"""

from cvpipeline.stages.stage5_shots import detect_shots


def _ball_frames(hits_at: list[float], duration_s: float, hz: float = 5) -> list[dict]:
    """hits_atで指定した時刻付近だけball_motionを閾値超えにした合成データ。"""
    frames = []
    t = 0.0
    step = 1 / hz
    while t <= duration_s:
        is_hit = any(abs(t - h) < step / 2 for h in hits_at)
        frames.append({"t": round(t, 2), "ball_motion": 0.6 if is_hit else 0.05})
        t += step
    return frames


def test_detect_shots_counts_distinct_hits():
    points = [{"start_s": 0.0, "end_s": 10.0}]
    ball_result = {"per_frame": _ball_frames([1.0, 3.0, 5.0, 7.0], duration_s=10.0)}
    shots = detect_shots(points, ball_result, degraded=False)
    assert len(shots) == 1
    assert len(shots[0]) == 4


def test_first_shot_is_serve_with_full_confidence():
    points = [{"start_s": 0.0, "end_s": 10.0}]
    ball_result = {"per_frame": _ball_frames([1.0, 3.0], duration_s=10.0)}
    shots = detect_shots(points, ball_result, degraded=False)[0]
    assert shots[0]["type"] == "serve"
    assert shots[0]["type_confidence"] == 1.0
    assert shots[1]["type"] == "unknown"
    assert shots[1]["type_confidence"] == 0.0


def test_last_shot_has_low_confidence_unknown_terminal():
    points = [{"start_s": 0.0, "end_s": 10.0}]
    ball_result = {"per_frame": _ball_frames([1.0, 3.0, 5.0], duration_s=10.0)}
    shots = detect_shots(points, ball_result, degraded=False)[0]
    assert "terminal" not in shots[0]
    assert "terminal" not in shots[1]
    assert shots[-1]["terminal"] == {"type": "unknown", "confidence": 0.2}


def test_degraded_mode_yields_no_shots():
    points = [{"start_s": 0.0, "end_s": 10.0}]
    ball_result = {"per_frame": _ball_frames([1.0, 3.0], duration_s=10.0)}
    shots = detect_shots(points, ball_result, degraded=True)
    assert shots == [[]]


def test_multiple_points_are_independent():
    points = [{"start_s": 0.0, "end_s": 4.0}, {"start_s": 6.0, "end_s": 10.0}]
    ball_result = {"per_frame": _ball_frames([1.0, 7.0, 9.0], duration_s=10.0)}
    shots = detect_shots(points, ball_result, degraded=False)
    assert len(shots[0]) == 1
    assert len(shots[1]) == 2
