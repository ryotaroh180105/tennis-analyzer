"""precheck → ingest → analyze → edit(cut/HLS/thumbnail) の実CVパイプライン疎通テスト。

実際にffmpeg/OpenCVを実行して動画を処理する統合テスト
（合成テニスコート風動画に対して、クラッシュなく妥当な出力が得られることを検証する）。
"""

from pathlib import Path

from cvpipeline.precheck import run_precheck


def test_precheck_detects_synthetic_court(synthetic_video):
    report = run_precheck(synthetic_video)
    assert report["input_valid"] is True
    assert report["checks"]["court"]["result"] in ("ok", "warn")
    assert report["meta"]["duration_s"] == 20.0


def test_ingest_normalizes_to_h264_with_correct_gop(tmp_path, synthetic_video):
    from cvpipeline.ingest import normalize

    out_path = str(tmp_path / "normalized.mp4")
    result = normalize(synthetic_video, out_path, encoder="libx264", gop_seconds=2, bitrate="2M")

    assert result["output_meta"]["codec"] == "h264"
    assert result["output_meta"]["duration_s"] == 20.0
    assert result["gop_frames"] == 60  # 2秒 x 30fps

    from app.editing.keyframes import list_keyframe_timestamps

    keyframes = list_keyframe_timestamps(out_path)
    assert len(keyframes) >= 8  # 20秒 / 2秒GOP でおよそ10個のキーフレームがあるはず
    assert keyframes[0] == 0.0


def test_analyze_produces_segments_within_video_bounds(tmp_path, synthetic_video):
    from cvpipeline.ingest import normalize
    from cvpipeline.pipeline import run_analyze

    normalized_path = str(tmp_path / "normalized.mp4")
    normalize(synthetic_video, normalized_path, encoder="libx264", gop_seconds=2, bitrate="2M")

    result = run_analyze(normalized_path, degraded=False)
    assert result["segments"], "少なくとも1つの区間が検出されるはず"
    for seg in result["segments"]:
        assert 0.0 <= seg["start_s"] < seg["end_s"] <= 20.0  # 動画長を超えない（実機検証で修正した回帰）

    # 13 D-1: ステージ別GPU秒の原価計測に使うstage_secondsが揃っていること
    assert set(result["stage_seconds"].keys()) == {"stage1_s", "stage2_s", "stage3_s", "stage4_s", "stage5_s"}
    assert all(v >= 0 for v in result["stage_seconds"].values())


def test_extract_stage_results_allows_downstream_only_rerun(tmp_path, synthetic_video):
    """13 C-1: stage1-3の出力（重い部分）を保存しておけば、stage4-5だけを再実行できる
    （segmentation.v1.yaml変更時などに動画の再ダウンロード・コート/選手/ボール再検出を
    やり直さずに済む。不変原則3）。
    """
    import json

    from cvpipeline.ingest import normalize
    from cvpipeline.pipeline import analyze_from_stage_results, extract_stage_results, run_analyze

    normalized_path = str(tmp_path / "normalized.mp4")
    normalize(synthetic_video, normalized_path, encoder="libx264", gop_seconds=2, bitrate="2M")

    stage_results = extract_stage_results(normalized_path, degraded=False)
    assert set(stage_results["stage_seconds"].keys()) == {"stage1_s", "stage2_s", "stage3_s"}

    # R2永続化を想定したJSON往復可能性（保存→再読込→下流のみ再実行、を模擬）
    round_tripped = json.loads(json.dumps(stage_results))

    from_split = analyze_from_stage_results(round_tripped)
    from_one_shot = run_analyze(normalized_path, degraded=False)

    assert from_split["segments"] == from_one_shot["segments"]
    assert from_split["event_stream_payload"] == from_one_shot["event_stream_payload"]
    assert set(from_split["stage_seconds"].keys()) == {"stage1_s", "stage2_s", "stage3_s", "stage4_s", "stage5_s"}


def test_full_pipeline_including_edit_and_hls(tmp_path, synthetic_video):
    from cvpipeline.ingest import normalize
    from cvpipeline.pipeline import run_analyze

    from app.editing.ffmpeg_ops import build_edited_video, build_hls, build_thumbnail

    normalized_path = str(tmp_path / "normalized.mp4")
    ingest_result = normalize(synthetic_video, normalized_path, encoder="libx264", gop_seconds=2, bitrate="2M")
    duration_s = ingest_result["output_meta"]["duration_s"]

    analyze_result = run_analyze(normalized_path, degraded=False)
    effective = [{"start_s": s["start_s"], "end_s": s["end_s"]} for s in analyze_result["segments"]]

    edited_path = str(tmp_path / "edited.mp4")
    build_edited_video(normalized_path, effective, duration_s, edited_path)
    assert Path(edited_path).exists()

    hls_dir = str(tmp_path / "hls")
    build_hls(edited_path, hls_dir)
    assert (Path(hls_dir) / "playlist.m3u8").exists()
    assert list(Path(hls_dir).glob("*.ts"))

    thumbnail_path = str(tmp_path / "thumb.jpg")
    build_thumbnail(edited_path, thumbnail_path)
    assert Path(thumbnail_path).exists()
