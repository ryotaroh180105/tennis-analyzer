"""ポイント勝敗の列から現在のスコアを合成する（純粋関数）。

自動判定はせず、ユーザーがワンタップで入力した勝敗（"self"/"opponent"）の列を
シングルス・ノーアド無し（デュース有り）・6ゲーム先取（6-6はタイブレーク）・
2セット先取のルールで畳み込む。三者以上の表記（ダブルスの個人内訳等）は
Phase 1の対象外（01 §Phase1: 自分/相手の識別のみ）。
"""

from typing import Literal

Side = Literal["self", "opponent"]

_GAME_POINT_LABELS = ["0", "15", "30", "40"]


def _other(side: Side) -> Side:
    return "opponent" if side == "self" else "self"


def _format_game(points: dict[Side, int]) -> dict[str, str]:
    p_self, p_opp = points["self"], points["opponent"]
    if p_self < 3 or p_opp < 3:
        return {"self": _GAME_POINT_LABELS[p_self], "opponent": _GAME_POINT_LABELS[p_opp]}
    if p_self == p_opp:
        return {"self": "Deuce", "opponent": "Deuce"}
    leader = "self" if p_self > p_opp else "opponent"
    return {leader: "Ad", _other(leader): "-"}


def compute_score(events: list[Side]) -> dict:
    sets: list[dict[str, int]] = []
    sets_won: dict[Side, int] = {"self": 0, "opponent": 0}
    set_games: dict[Side, int] = {"self": 0, "opponent": 0}
    game_points: dict[Side, int] = {"self": 0, "opponent": 0}
    tiebreak_points: dict[Side, int] = {"self": 0, "opponent": 0}
    in_tiebreak = False
    match_winner: Side | None = None

    for winner in events:
        if match_winner is not None:
            break
        loser = _other(winner)

        if in_tiebreak:
            tiebreak_points[winner] += 1
            if tiebreak_points[winner] >= 7 and tiebreak_points[winner] - tiebreak_points[loser] >= 2:
                set_games[winner] += 1
                sets.append(dict(set_games))
                sets_won[winner] += 1
                set_games = {"self": 0, "opponent": 0}
                game_points = {"self": 0, "opponent": 0}
                tiebreak_points = {"self": 0, "opponent": 0}
                in_tiebreak = False
                if sets_won[winner] >= 2:
                    match_winner = winner
            continue

        game_points[winner] += 1
        if game_points[winner] >= 4 and game_points[winner] - game_points[loser] >= 2:
            set_games[winner] += 1
            game_points = {"self": 0, "opponent": 0}
            if set_games[winner] >= 6 and set_games[winner] - set_games[loser] >= 2:
                sets.append(dict(set_games))
                sets_won[winner] += 1
                set_games = {"self": 0, "opponent": 0}
                if sets_won[winner] >= 2:
                    match_winner = winner
            elif set_games["self"] == 6 and set_games["opponent"] == 6:
                in_tiebreak = True

    return {
        "completed_sets": sets,
        "current_set_games": set_games,
        "current_game": {"self": game_points["self"], "opponent": game_points["opponent"]},
        "current_game_display": _format_game(game_points) if not in_tiebreak else None,
        "tiebreak": tiebreak_points if in_tiebreak else None,
        "match_winner": match_winner,
        "total_points": len(events),
    }
