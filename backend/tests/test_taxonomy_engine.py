"""ミス分類ルールエンジンのユニットテスト（config/taxonomy.v1.yaml準拠）。"""

import copy

import pytest

from app.services.taxonomy_engine import _validate_taxonomy, classify_point, evaluate_when, load_taxonomy


@pytest.fixture
def taxonomy():
    return load_taxonomy()


def _valid_taxonomy() -> dict:
    return {
        "dimensions": [
            {
                "id": "shot_type",
                "source": "cv.shot.type",
                "values": ["serve", "unknown"],
                "labels": {"ja": {"serve": "サーブ", "unknown": "未分類"}},
            },
            {
                "id": "pressure",
                "source": "rule",
                "values": ["forced", "unforced"],
                "labels": {"ja": {"forced": "強制", "unforced": "非強制"}},
                "rules": [
                    {"value": "forced", "when": "shot.landing_depth > thresholds.forcing_depth"},
                    {"value": "unforced", "when": "default"},
                ],
            },
        ],
        "thresholds": {"forcing_depth": 0.8, "rally_long": 9},
        "labels": [{"match": {}, "label": {"ja": "その他"}}],
        "tags": [
            {"id": "weak_ball", "label": {"ja": "甘い球"}, "when": "shot.landing_depth < thresholds.forcing_depth"},
            {
                "id": "long_rally",
                "label": {"ja": "ロングラリー"},
                "scope": "point",
                "when": "point.shot_count >= thresholds.rally_long",
            },
        ],
    }


def test_validate_taxonomy_accepts_well_formed_config():
    _validate_taxonomy(_valid_taxonomy())  # raises on failure


def test_validate_taxonomy_rejects_unknown_field_in_rule_when():
    cfg = _valid_taxonomy()
    cfg["dimensions"][1]["rules"][0]["when"] = "shot.landing_deptttth > thresholds.forcing_depth"
    with pytest.raises(ValueError, match="unknown field"):
        _validate_taxonomy(cfg)


def test_validate_taxonomy_rejects_unknown_thresholds_key():
    cfg = _valid_taxonomy()
    cfg["tags"][0]["when"] = "shot.landing_depth < thresholds.does_not_exist"
    with pytest.raises(ValueError, match="unknown thresholds key"):
        _validate_taxonomy(cfg)


def test_validate_taxonomy_rejects_missing_catch_all_label():
    cfg = _valid_taxonomy()
    cfg["labels"] = [{"match": {"shot_type": "serve"}, "label": {"ja": "サーブ"}}]
    with pytest.raises(ValueError, match="catch-all"):
        _validate_taxonomy(cfg)


def test_validate_taxonomy_rejects_rule_dimension_without_default():
    cfg = _valid_taxonomy()
    cfg["dimensions"][1]["rules"] = [{"value": "forced", "when": "shot.landing_depth > thresholds.forcing_depth"}]
    with pytest.raises(ValueError, match="default rule"):
        _validate_taxonomy(cfg)


def test_validate_taxonomy_rejects_incomplete_label_locale():
    cfg = _valid_taxonomy()
    cfg["dimensions"][0]["labels"]["ja"] = {"serve": "サーブ"}  # "unknown" キー欠落
    with pytest.raises(ValueError, match="missing keys"):
        _validate_taxonomy(cfg)


def test_validate_taxonomy_rejects_label_match_unknown_value():
    cfg = _valid_taxonomy()
    cfg["labels"].insert(0, {"match": {"shot_type": "backhand"}, "label": {"ja": "バックハンド"}})
    with pytest.raises(ValueError, match="unknown values"):
        _validate_taxonomy(cfg)


def test_load_taxonomy_real_config_is_deep_copyable():
    # 実configがバリデータを通ること自体は load_taxonomy() 呼び出しで担保済み（fixture参照）。
    # ここでは破壊的変更に対する回帰として、コピーしても検証結果が変わらないことを確認する。
    _validate_taxonomy(copy.deepcopy(load_taxonomy()))


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
