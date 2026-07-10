"""即時フィードバック文面生成（07-advice-delivery.md §配信の3層設計 ①）。

「何を言うか」（advice_engine.evaluate_triggers が判定するトリガー）と
「どう言うか」（ここ、Claude APIでの文面生成）の分業。
Claude APIに渡すのは集計済み構造化スタッツJSONのみ。動画・イベントストリーム・
個々のショット系列は一切渡さない（CLAUDE.md 不変原則4）。
"""

import json
from functools import lru_cache

import anthropic
from pydantic import BaseModel, Field

from app.core.config import get_settings

SYSTEM_PROMPT = """あなたは日本のテニス愛好家向けアプリのコーチアシスタントです。
ユーザーが撮影した試合のミス分類集計（JSON）から、直後に届ける短いフィードバックを作成します。

トーン・制約（厳守）：
- 断定しない。「〜の傾向が見られました」「〜かもしれません」のような柔らかい言い切りにする。
- ポジティブな点を必ず先に触れる。ダメ出しだけで終わらない。
- 集計サンプルが少ない・未分類が多い場合は、断定的な分析をせず「データが少なくまだ傾向を掴みきれていません」
  という趣旨を正直に伝える（誤った断定より不明を優先する）。
- ミス傾向は最大3件、練習提案は最大2件。件数を無理に埋めない（材料が無ければ空配列でよい）。
- 練習提案は「何を・どれくらい」まで具体的にする（例："クロスラリーを20本連続で"）。
- 選手名・プロ選手との比較・映像そのものへの言及はしない（渡されるのは集計値のみ）。
"""


class ImmediateFeedback(BaseModel):
    summary: str = Field(description="試合全体の総括。1〜2文。")
    tendencies: list[str] = Field(description="見られたミス傾向。断定しない言い切り。最大3件。")
    drill_suggestions: list[str] = Field(description="次回試すと良い具体的なドリル提案。最大2件。")


@lru_cache
def _client() -> anthropic.Anthropic:
    settings = get_settings()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def generate_immediate_feedback(
    stats: dict, metrics: dict, client: anthropic.Anthropic | None = None
) -> ImmediateFeedback:
    """stats: services.stats.aggregate_stats() の出力、metrics: compute_match_metrics() の出力。

    どちらも動画・イベントストリームを含まない集計済みJSON（不変原則4）。
    """
    settings = get_settings()
    payload = {
        "total_points": stats["total_points"],
        "unclassified_points": stats["unclassified_points"],
        "labels": stats["labels"],
        "serve_fault_rate": metrics["serve_fault_rate"],
        "by_shot_type": metrics["by_shot_type"],
    }
    response = (client or _client()).messages.parse(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        output_format=ImmediateFeedback,
    )
    return response.parsed_output
