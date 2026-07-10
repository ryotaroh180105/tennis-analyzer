"""スタッツ集計のユニットテスト。"""

from app.services.stats import aggregate_stats


def _payload(points):
    return {"points": points}


def test_all_unclassified_when_cv_confidence_is_low():
    payload = _payload(
        [
            {
                "index": 0,
                "clip": {"start_s": 0.0, "end_s": 10.0},
                "shot_count": 2,
                "shots": [
                    {"index": 0, "type": "serve", "type_confidence": 1.0},
                    {"index": 1, "type": "unknown", "type_confidence": 0.0, "terminal": {"type": "unknown", "confidence": 0.2}},
                ],
            }
        ]
    )
    result = aggregate_stats(payload)
    assert result["total_points"] == 1
    assert result["unclassified_points"] == 1
    assert result["stat_counts"] == {}
    assert result["labels"] == []


def test_highlight_from_winner_label():
    payload = _payload(
        [
            {
                "index": 0,
                "clip": {"start_s": 5.0, "end_s": 15.0},
                "shot_count": 2,
                "shots": [
                    {"index": 0, "type": "serve", "type_confidence": 1.0},
                    {"index": 1, "type": "forehand", "type_confidence": 0.9, "terminal": {"type": "winner", "confidence": 0.9}},
                ],
            }
        ]
    )
    result = aggregate_stats(payload)
    assert result["unclassified_points"] == 0
    assert len(result["highlights"]) == 1
    assert result["highlights"][0] == {
        "point_index": 0,
        "start_s": 5.0,
        "end_s": 15.0,
        "label": "ウィナー",
        "importance": "high",
        "tags": [],
    }
    assert result["labels"][0]["label"] == "ウィナー"
    assert result["labels"][0]["count"] == 1


def test_serve_fault_stat_key_counted():
    payload = _payload(
        [
            {
                "index": 0,
                "clip": {"start_s": 0.0, "end_s": 5.0},
                "shot_count": 1,
                "shots": [{"index": 0, "type": "serve", "type_confidence": 1.0, "terminal": {"type": "net", "confidence": 0.9}}],
            }
        ]
    )
    result = aggregate_stats(payload)
    assert result["stat_counts"] == {"serve_fault": 1}


def test_empty_points():
    result = aggregate_stats(_payload([]))
    assert result["total_points"] == 0
    assert result["unclassified_points"] == 0
    assert result["highlights"] == []
