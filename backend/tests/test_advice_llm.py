"""即時フィードバック生成のユニットテスト。実APIは呼ばずクライアントをスタブする。"""

import json

from app.services.advice_llm import ImmediateFeedback, generate_immediate_feedback


class _FakeResponse:
    def __init__(self, parsed_output):
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self):
        self.last_call = None

    def parse(self, **kwargs):
        self.last_call = kwargs
        return _FakeResponse(
            ImmediateFeedback(
                summary="接戦を制しました。",
                tendencies=["バックハンドでのネットミスがやや目立ちました。"],
                drill_suggestions=["クロスラリーを20本連続で。"],
            )
        )


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def _stats():
    return {
        "total_points": 10,
        "unclassified_points": 2,
        "labels": [{"label": "ネットミス", "importance": "medium", "count": 3}],
        "highlights": [],
        "stat_counts": {},
    }


def _metrics():
    return {
        "points": 10,
        "serve_fault_rate": 0.3,
        "double_faults": None,
        "loss_rate_by_rally": {},
        "by_shot_type": {"backhand": {"unforced_error_rate": 0.4}},
    }


def test_generate_immediate_feedback_returns_parsed_output():
    client = _FakeClient()
    result = generate_immediate_feedback(_stats(), _metrics(), client=client)
    assert isinstance(result, ImmediateFeedback)
    assert result.summary == "接戦を制しました。"
    assert result.tendencies == ["バックハンドでのネットミスがやや目立ちました。"]


def test_generate_immediate_feedback_never_sends_shots_or_video_fields():
    # CLAUDE.md 不変原則4: 動画をLLMに渡さない。ショット単位の生データも渡さない。
    client = _FakeClient()
    generate_immediate_feedback(_stats(), _metrics(), client=client)
    sent = client.messages.last_call["messages"][0]["content"]
    payload = json.loads(sent)
    assert "shots" not in payload
    assert "points" not in payload or not isinstance(payload.get("points"), list)
    assert set(payload.keys()) == {
        "total_points",
        "unclassified_points",
        "labels",
        "serve_fault_rate",
        "by_shot_type",
    }


def test_generate_immediate_feedback_uses_configured_model():
    client = _FakeClient()
    generate_immediate_feedback(_stats(), _metrics(), client=client)
    assert client.messages.last_call["output_format"] is ImmediateFeedback
    assert client.messages.last_call["model"]
