"""各CVステージを stage_input.json → stage_output.json の独立CLIとして実行する
（ゴールデンセット回帰・デバッグ用、不変原則3・10 §ステージ間の入出力契約）。

使い方:
    python -m cvpipeline.stage_cli <stage> <input.json> <output.json>

<stage> は stage1|stage2|stage3|stage4|stage5。各ステージの入力JSONの形は
下記 _STAGE_RUNNERS のkwargs抽出ロジックを参照（10のステージ間契約と対応）。
"""

import argparse
import json
import sys


def _run_stage1(payload: dict) -> dict:
    from cvpipeline.stages.stage1_court import detect_court

    return detect_court(payload["video_path"], sample_seconds=payload.get("sample_seconds", 3.0))


def _run_stage2(payload: dict) -> dict:
    from cvpipeline.stages.stage2_players import analyze_person_motion

    return analyze_person_motion(
        payload["video_path"],
        payload.get("court_polygon_px"),
        hz=payload["hz"],
        max_seconds=payload.get("max_seconds"),
        degraded=payload.get("degraded", False),
    )


def _run_stage3(payload: dict) -> dict:
    from cvpipeline.stages.stage3_ball import analyze_ball_motion

    return analyze_ball_motion(payload["video_path"], hz=payload["hz"], max_seconds=payload.get("max_seconds"))


def _run_stage4(payload: dict) -> dict:
    from cvpipeline.stages.stage4_segments import segment_points

    return segment_points(
        payload["person_result"],
        payload["ball_result"],
        degraded=payload.get("degraded", False),
        duration_s=payload.get("duration_s"),
    )


def _run_stage5(payload: dict) -> dict:
    from cvpipeline.stages.stage5_shots import detect_shots

    shots_by_point = detect_shots(payload["points"], payload["ball_result"], degraded=payload.get("degraded", False))
    return {"shots_by_point": shots_by_point}


_STAGE_RUNNERS = {
    "stage1": _run_stage1,
    "stage2": _run_stage2,
    "stage3": _run_stage3,
    "stage4": _run_stage4,
    "stage5": _run_stage5,
}


def run_stage(stage: str, payload: dict) -> dict:
    if stage not in _STAGE_RUNNERS:
        raise ValueError(f"unknown stage: {stage!r} (must be one of {sorted(_STAGE_RUNNERS)})")
    return _STAGE_RUNNERS[stage](payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=sorted(_STAGE_RUNNERS))
    parser.add_argument("input_path", help="stage_input.json")
    parser.add_argument("output_path", help="stage_output.json (書き込み先)")
    args = parser.parse_args(argv)

    with open(args.input_path, encoding="utf-8") as f:
        payload = json.load(f)

    result = run_stage(args.stage, payload)

    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
