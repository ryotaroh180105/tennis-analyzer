"""スコア合成ロジック（純粋関数）のユニットテスト。01 §Phase1 半自動スコア入力。"""

from app.services.scoring import compute_score


def test_empty_events_start_at_love_all():
    result = compute_score([])
    assert result["current_game"] == {"self": 0, "opponent": 0}
    assert result["current_game_display"] == {"self": "0", "opponent": "0"}
    assert result["completed_sets"] == []
    assert result["match_winner"] is None


def test_game_point_labels():
    result = compute_score(["self", "self", "self"])
    assert result["current_game_display"] == {"self": "40", "opponent": "0"}


def test_deuce_and_advantage():
    result = compute_score(["self", "opponent", "self", "opponent", "self", "opponent"])
    assert result["current_game_display"] == {"self": "Deuce", "opponent": "Deuce"}

    result = compute_score(["self", "opponent", "self", "opponent", "self", "opponent", "self"])
    assert result["current_game_display"] == {"self": "Ad", "opponent": "-"}


def test_win_game_from_advantage():
    events = ["self", "opponent", "self", "opponent", "self", "opponent", "self", "self"]
    result = compute_score(events)
    assert result["current_set_games"] == {"self": 1, "opponent": 0}
    assert result["current_game"] == {"self": 0, "opponent": 0}


def test_win_set_at_six_games():
    events = []
    for _ in range(6):
        events += ["self"] * 4
    result = compute_score(events)
    assert result["completed_sets"] == [{"self": 6, "opponent": 0}]
    assert result["current_set_games"] == {"self": 0, "opponent": 0}


def test_tiebreak_at_six_all():
    events = []
    for i in range(12):
        events += ["self" if i % 2 == 0 else "opponent"] * 4
    result = compute_score(events)
    assert result["current_set_games"] == {"self": 6, "opponent": 6}
    assert result["tiebreak"] == {"self": 0, "opponent": 0}
    assert result["current_game_display"] is None

    events += ["self"] * 7
    result = compute_score(events)
    assert result["completed_sets"][-1] == {"self": 7, "opponent": 6}


def test_match_winner_at_two_sets():
    events = []
    for _ in range(2):
        for _ in range(6):
            events += ["self"] * 4
    result = compute_score(events)
    assert result["match_winner"] == "self"
    assert len(result["completed_sets"]) == 2


def test_events_after_match_winner_are_ignored():
    events = []
    for _ in range(2):
        for _ in range(6):
            events += ["self"] * 4
    events += ["opponent"] * 10
    result = compute_score(events)
    assert result["match_winner"] == "self"
    assert len(result["completed_sets"]) == 2
