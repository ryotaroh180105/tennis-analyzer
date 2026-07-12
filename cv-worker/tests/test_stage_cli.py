"""各ステージの独立CLI（stage_input.json → stage_output.json）のテスト。

10 §「各ステージは stage_input.json → stage_output.json の独立CLIとしても実行可能に
する（ゴールデンセット回帰・デバッグ用。不変原則3）」の実装確認。
"""

import json

import pytest

from cvpipeline.stage_cli import main, run_stage


def test_run_stage_rejects_unknown_stage_name():
    with pytest.raises(ValueError, match="unknown stage"):
        run_stage("stage9", {})


def test_stage1_cli_produces_valid_output_shape(synthetic_video):
    result = run_stage("stage1", {"video_path": synthetic_video, "sample_seconds": 2.0})
    assert set(result.keys()) == {
        "court_detected",
        "homography",
        "court_polygon_px",
        "court_type",
        "confidence",
        "spec_version",
    }
    json.dumps(result)  # JSON往復可能であること（ファイル出力契約の前提）


def test_stage2_cli_produces_valid_output_shape(synthetic_video):
    result = run_stage(
        "stage2",
        {"video_path": synthetic_video, "court_polygon_px": None, "hz": 5, "max_seconds": 3.0, "degraded": True},
    )
    assert set(result.keys()) == {"hz", "per_frame", "confidence"}
    json.dumps(result)


def test_stage3_cli_produces_valid_output_shape(synthetic_video):
    result = run_stage("stage3", {"video_path": synthetic_video, "hz": 5, "max_seconds": 3.0})
    assert set(result.keys()) == {"hz", "per_frame", "confidence"}
    json.dumps(result)


def test_stage4_cli_consumes_stage2_and_stage3_outputs(synthetic_video):
    person_result = run_stage(
        "stage2",
        {"video_path": synthetic_video, "court_polygon_px": None, "hz": 5, "max_seconds": 3.0, "degraded": True},
    )
    ball_result = run_stage("stage3", {"video_path": synthetic_video, "hz": 5, "max_seconds": 3.0})
    result = run_stage(
        "stage4", {"person_result": person_result, "ball_result": ball_result, "degraded": True, "duration_s": 20.0}
    )
    assert set(result.keys()) == {"segments", "params_version"}
    json.dumps(result)


def test_stage5_cli_consumes_stage4_output(synthetic_video):
    ball_result = run_stage("stage3", {"video_path": synthetic_video, "hz": 5, "max_seconds": 3.0})
    result = run_stage("stage5", {"points": [], "ball_result": ball_result, "degraded": True})
    assert result == {"shots_by_point": []}


def test_cli_main_reads_input_json_and_writes_output_json(tmp_path, synthetic_video):
    input_path = tmp_path / "stage_input.json"
    output_path = tmp_path / "stage_output.json"
    input_path.write_text(json.dumps({"video_path": synthetic_video, "sample_seconds": 2.0}), encoding="utf-8")

    exit_code = main(["stage1", str(input_path), str(output_path)])

    assert exit_code == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert "court_detected" in written
