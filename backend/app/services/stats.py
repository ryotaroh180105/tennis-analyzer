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
