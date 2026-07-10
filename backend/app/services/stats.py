"""試合のミス分類集計（04-miss-taxonomy.md）。

exclude_from_stats のポイントは分母から除外し「未分類 n件」として別集計する
（taxonomy.v1.yaml のコメント通りの挙動）。
"""

from app.services.taxonomy_engine import classify_event_stream, load_taxonomy


def aggregate_stats(payload: dict) -> dict:
    taxonomy = load_taxonomy()
    classified = classify_event_stream(payload, taxonomy)
    points_by_index = {p["index"]: p for p in payload.get("points", [])}

    total_points = len(classified)
    unclassified_points = 0
    stat_counts: dict[str, int] = {}
    label_counts: dict[str, dict] = {}
    highlights: list[dict] = []

    for point_result in classified:
        idx = point_result["point_index"]
        point = points_by_index.get(idx, {})
        shots = point_result["shots"]
        terminal_shot = shots[-1] if shots else None

        if terminal_shot is None or terminal_shot["exclude_from_stats"]:
            unclassified_points += 1
        else:
            label_text = terminal_shot["label"].get("ja", "")
            entry = label_counts.setdefault(
                label_text, {"label": label_text, "importance": terminal_shot["importance"], "count": 0}
            )
            entry["count"] += 1
            if terminal_shot.get("stat_key"):
                stat_counts[terminal_shot["stat_key"]] = stat_counts.get(terminal_shot["stat_key"], 0) + 1

        is_highlight = bool(terminal_shot and terminal_shot["highlight"]) or "long_rally" in point_result["tags"]
        if is_highlight:
            clip = point.get("clip", {})
            highlights.append(
                {
                    "point_index": idx,
                    "start_s": clip.get("start_s"),
                    "end_s": clip.get("end_s"),
                    "label": terminal_shot["label"].get("ja", "") if terminal_shot else None,
                    "importance": terminal_shot["importance"] if terminal_shot else "none",
                    "tags": point_result["tags"],
                }
            )

    return {
        "total_points": total_points,
        "unclassified_points": unclassified_points,
        "stat_counts": stat_counts,
        "labels": sorted(label_counts.values(), key=lambda e: -e["count"]),
        "highlights": highlights,
    }


def compute_match_metrics(payload: dict) -> dict:
    """advice-rules.v1.yaml のトリガー評価が参照する試合単位のメトリクス。

    「相手ではなく自分が打った/失った」の判定に必要な打者帰属（誰が打ったか）は
    未実装のため、loss_rate_by_rally は算出不能（常に空。07のwhen式は安全にFalseへ倒れる。
    CLAUDE.md 不変原則1）。
    """
    taxonomy = load_taxonomy()
    classified = classify_event_stream(payload, taxonomy)

    by_shot_type: dict[str, dict[str, int]] = {}
    serve_total = 0
    serve_fault = 0

    for point_result in classified:
        for shot in point_result["shots"]:
            shot_type = shot["shot_type"]
            if shot_type in ("backhand", "forehand"):
                counts = by_shot_type.setdefault(shot_type, {"total": 0, "unforced_errors": 0})
                counts["total"] += 1
                if shot["outcome"] in ("net", "out") and shot["pressure"] == "unforced":
                    counts["unforced_errors"] += 1
            if shot_type == "serve":
                serve_total += 1
                if shot.get("stat_key") == "serve_fault":
                    serve_fault += 1

    return {
        "points": len(classified),
        "serve_fault_rate": (serve_fault / serve_total) if serve_total else None,
        "double_faults": None,  # serve_number軸（1st/2nd識別）未実装のため算出不能（taxonomy v2予定）
        "loss_rate_by_rally": {},  # 打者帰属未実装のため算出不能
        "by_shot_type": {
            shot_type: {
                "unforced_error_rate": (counts["unforced_errors"] / counts["total"]) if counts["total"] else None
            }
            for shot_type, counts in by_shot_type.items()
        },
    }
