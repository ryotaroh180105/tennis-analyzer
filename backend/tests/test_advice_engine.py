"""アドバイス発火ルールエンジンのユニットテスト（config/advice-rules.v1.yaml準拠）。"""

import pytest

from app.services.advice_engine import (
    AdviceEvalContext,
    evaluate_triggers,
    evaluate_when,
    load_advice_rules,
)


@pytest.fixture
def rules():
    return load_advice_rules()


def _match(
    *,
    serve_fault_rate=None,
    double_faults=None,
    points=40,
    backhand_uer=None,
    forehand_uer=None,
    loss_rate_by_rally=None,
):
    by_shot_type = {}
    if backhand_uer is not None:
        by_shot_type["backhand"] = {"unforced_error_rate": backhand_uer}
    if forehand_uer is not None:
        by_shot_type["forehand"] = {"unforced_error_rate": forehand_uer}
    return {
        "points": points,
        "serve_fault_rate": serve_fault_rate,
        "double_faults": double_faults,
        "loss_rate_by_rally": loss_rate_by_rally or {},
        "by_shot_type": by_shot_type,
    }


def test_evaluate_when_rejects_disallowed_syntax():
    ctx = AdviceEvalContext([_match()])
    with pytest.raises(ValueError):
        evaluate_when("__import__('os').system('echo hi')", ctx)


def test_trend_rising_backhand_unforced_error_fires(rules):
    history = [
        _match(backhand_uer=0.10),
        _match(backhand_uer=0.20),
        _match(backhand_uer=0.30),
    ]
    fired = evaluate_triggers(history, rules=rules)
    ids = [t["id"] for t in fired]
    assert "backhand_unforced_trend" in ids


def test_trend_flat_backhand_unforced_error_does_not_fire(rules):
    history = [
        _match(backhand_uer=0.20),
        _match(backhand_uer=0.20),
        _match(backhand_uer=0.20),
    ]
    fired = evaluate_triggers(history, rules=rules)
    ids = [t["id"] for t in fired]
    assert "backhand_unforced_trend" not in ids


def test_serve_fault_spike_fires_when_recent_baseline_is_low(rules):
    history = [
        _match(serve_fault_rate=0.30),
        _match(serve_fault_rate=0.32),
        _match(serve_fault_rate=0.28),
        _match(serve_fault_rate=0.31),
        _match(serve_fault_rate=0.50),
    ]
    fired = evaluate_triggers(history, rules=rules)
    ids = [t["id"] for t in fired]
    assert "serve_fault_spike" in ids


def test_serve_fault_spike_does_not_fire_when_baseline_already_high(rules):
    history = [
        _match(serve_fault_rate=0.40),
        _match(serve_fault_rate=0.40),
        _match(serve_fault_rate=0.40),
        _match(serve_fault_rate=0.40),
        _match(serve_fault_rate=0.50),
    ]
    fired = evaluate_triggers(history, rules=rules)
    ids = [t["id"] for t in fired]
    assert "serve_fault_spike" not in ids


def test_double_fault_spike_is_disabled_even_when_condition_met(rules):
    history = [_match(double_faults=1), _match(double_faults=1), _match(double_faults=6)]
    fired = evaluate_triggers(history, rules=rules)
    ids = [t["id"] for t in fired]
    assert "double_fault_spike" not in ids


def test_short_rally_losses_missing_data_never_fires(rules):
    # loss_rate_by_rally は打者帰属未実装のため常に空 → last_match.loss_rate_by_rally('1-4') は None
    # → 比較は例外にならず安全にFalseへ倒れる（不変原則1）
    history = [_match(points=50, loss_rate_by_rally={})]
    fired = evaluate_triggers(history, rules=rules)
    ids = [t["id"] for t in fired]
    assert "short_rally_losses" not in ids


def test_short_rally_losses_fires_with_sufficient_data(rules):
    history = [_match(points=50, loss_rate_by_rally={"1-4": 0.70})]
    fired = evaluate_triggers(history, rules=rules)
    ids = [t["id"] for t in fired]
    assert "short_rally_losses" in ids


def test_improvement_praise_uses_external_flag(rules):
    history = [_match()]
    assert evaluate_triggers(history, improved_since_last_advice=True, rules=rules)
    fired_ids = [t["id"] for t in evaluate_triggers(history, improved_since_last_advice=True, rules=rules)]
    assert "improvement_praise" in fired_ids
    fired_ids_false = [t["id"] for t in evaluate_triggers(history, improved_since_last_advice=False, rules=rules)]
    assert "improvement_praise" not in fired_ids_false


def test_fired_triggers_sorted_by_priority_descending(rules):
    history = [
        _match(backhand_uer=0.10, serve_fault_rate=0.30),
        _match(backhand_uer=0.20, serve_fault_rate=0.31),
        _match(backhand_uer=0.30, serve_fault_rate=0.28),
        _match(serve_fault_rate=0.29),
        _match(serve_fault_rate=0.50),
    ]
    fired = evaluate_triggers(history, improved_since_last_advice=True, rules=rules)
    priorities = [t["priority"] for t in fired]
    assert priorities == sorted(priorities, reverse=True)


def test_empty_match_history_fires_nothing(rules):
    assert evaluate_triggers([], rules=rules) == []
