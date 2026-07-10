"""ミス分類ルールエンジンのユニットテスト（config/taxonomy.v1.yaml準拠）。"""

import pytest

from app.services.taxonomy_engine import classify_point, evaluate_when, load_taxonomy


@pytest.fixture
def taxonomy():
    return load_taxonomy()


def test_evaluate_when_default_is_always_true():
    assert evaluate_when("default", {}) is True


def test_evaluate_when_simple_comparison():
    assert evaluate_when("shot.landing_depth > thresholds.x", {"shot": {"landing_depth": 0.9}, "thresholds": {"x": 0.5}})
    assert not evaluate_when("shot.landing_depth > thresholds.x", {"shot": {"landing_depth": 0.1}, "thresholds": {"x": 0.5}})


def test_evaluate_when_missing_field_is_false_not_error():
    # shot.landing_depth が存在しない → 比較不成立（例外にしない。不変原則1）
    assert not evaluate_when("shot.landing_depth > thresholds.x", {"shot": {}, "thresholds": {"x": 0.5}})


def test_evaluate_when_or_and_and():
    ctx = {"a": {"v": 1}, "b": {"v": 5}}
    assert evaluate_when("a.v > 5 or b.v > 3", ctx)
    assert not evaluate_when("a.v > 5 and b.v > 3", ctx)


def test_evaluate_when_rejects_disallowed_syntax():
    with pytest.raises(ValueError):
        evaluate_when("__import__('os').system('echo hi')", {})
    with pytest.raises(ValueError):
        evaluate_when("[x for x in range(3)]", {})


def _point(shots):
    return {"index": 0, "shot_count": len(shots), "shots": shots}


def test_serve_with_unknown_outcome_falls_to_uncategorized(taxonomy):
    # stage5の現行dev CVでは非terminalショットはunknown、terminalも低confidenceのunknown
    shots = [
        {"index": 0, "type": "serve", "type_confidence": 1.0},
        {"index": 1, "type": "unknown", "type_confidence": 0.0, "terminal": {"type": "unknown", "confidence": 0.2}},
    ]
    result = classify_point(_point(shots), taxonomy)
    last = result["shots"][-1]
    assert last["outcome"] == "unknown"
    assert last["exclude_from_stats"] is True
    assert last["label"]["ja"] == "未分類ポイント"


def test_non_terminal_shot_is_in_play(taxonomy):
    shots = [
        {"index": 0, "type": "serve", "type_confidence": 1.0},
        {"index": 1, "type": "unknown", "type_confidence": 0.0},
        {"index": 2, "type": "unknown", "type_confidence": 0.0, "terminal": {"type": "unknown", "confidence": 0.2}},
    ]
    result = classify_point(_point(shots), taxonomy)
    assert result["shots"][0]["outcome"] == "in_play"
    assert result["shots"][1]["outcome"] == "in_play"


def test_long_rally_tag_fires_on_point_scope(taxonomy):
    rally_long = taxonomy["thresholds"]["rally_long"]
    shots = [{"index": i, "type": "serve" if i == 0 else "unknown", "type_confidence": 1.0 if i == 0 else 0.0} for i in range(rally_long)]
    shots[-1]["terminal"] = {"type": "unknown", "confidence": 0.2}
    result = classify_point(_point(shots), taxonomy)
    assert "long_rally" in result["tags"]


def test_short_rally_does_not_get_long_rally_tag(taxonomy):
    shots = [
        {"index": 0, "type": "serve", "type_confidence": 1.0},
        {"index": 1, "type": "unknown", "type_confidence": 0.0, "terminal": {"type": "unknown", "confidence": 0.2}},
    ]
    result = classify_point(_point(shots), taxonomy)
    assert "long_rally" not in result["tags"]


def test_high_confidence_synthetic_winner_matches_winner_label(taxonomy):
    # min_confidenceを満たす合成データでラベルマッチングの経路自体を検証する
    # （現行CVはこの信頼度を出さないが、将来の実装差し替え後の互換性を担保する）
    shots = [
        {"index": 0, "type": "serve", "type_confidence": 1.0},
        {"index": 1, "type": "forehand", "type_confidence": 0.9, "terminal": {"type": "winner", "confidence": 0.9}},
    ]
    result = classify_point(_point(shots), taxonomy)
    last = result["shots"][-1]
    assert last["outcome"] == "winner"
    assert last["label"]["ja"] == "ウィナー"
    assert last["highlight"] is True
