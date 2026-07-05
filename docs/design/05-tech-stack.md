# 05. 技術選定（外部ツール連携）

方針：**自前実装は最小化**し、実績のあるOSS・APIを接着する。
選定基準は (a) スマホ1台動画での実績、(b) ライセンスの商用利用可否、(c) 運用コスト。

## コンピュータビジョン

| 用途 | 第一候補 | 代替 | 備考 |
|---|---|---|---|
| 選手検出 | YOLO系（例: RT-DETR / YOLOX ※Apache-2.0系を優先） | Ultralytics YOLO（AGPL/商用ライセンス要検討） | ライセンス注意。人物クラスのみで十分 |
| 選手追跡 | ByteTrack | BoT-SORT | 2名固定なのでシンプルで足りる |
| ボール検出・追跡 | TrackNet系（時系列ヒートマップCNN、テニス実績多数） | 自前の小型時系列モデル | 小さく速い物体は単フレーム検出では不可。3フレーム入力型が定石 |
| コート検出 | 白線検出＋RANSACホモグラフィ（自前の薄い実装） | 学習ベースのコートキーポイント検出 | オムニコートのデータ収集が鍵（[03](03-recording-guidelines.md)）。**コート寸法・ライン定義はコードにハードコードせず `court-spec.yaml` として持つ**（将来のパデル・ピックルボール展開時にCV側の改修範囲を限定する規約） |
| 姿勢推定 | MediaPipe Pose（Tasks API） | MMPose（精度重視の再解析用） | まずMediaPipe。33ランドマーク＋visibility。バイオメカ指標は自前算出 |

- GPUワーカーはコンテナ化し、需要に応じてスケール（初期はサーバーレスGPUのジョブ単位課金。
  常駐なし。[08](08-operations.md)）。
- モデルの中間出力（検出ボックス、軌道、骨格）はすべて保存し、モデル更新時の回帰評価に使う。

## 動画処理・配信

| 用途 | 選定 | 備考 |
|---|---|---|
| カット・連結・オーバーレイ | FFmpeg | キーフレームスナップで `-c copy` を優先し高速化 |
| 配信 | HLS + S3互換ストレージ + CDN | 署名付きURLで共有リンク。Muxなどの有償サービスは規模が出てから検討 |
| ストレージ | Cloudflare R2（egress無料）または S3 | 動画は配信コストが支配的。R2優位 |
| サムネイル/プレビュー | FFmpeg (`thumbnail`, スプライト) | ハイライト選定UIで使用 |

## バックエンド / フロントエンド

| 層 | 選定 | 理由 |
|---|---|---|
| API | Python / FastAPI | CVエコシステムと同一言語で運用が単純 |
| 非同期ジョブ | Celery + Redis | 解析・エンコードのジョブキュー |
| DB | PostgreSQL | イベントストリームはJSONB、集計はSQL |
| フロント | Next.js（PWA） | クロスプラットフォームを最小工数で確保（AceSense等も対応済みのため差別化の主軸ではなく補助。[09](09-go-to-market.md)）。**ネイティブ移行はオンデバイスCV（端末側前処理・粗カット）が必要になった時点で判断**（[08](08-operations.md) の移行トリガー参照） |
| 通知・共有 | LINE Messaging API（日本のターゲット層に最適）、YouTube Data API（限定公開アップロード、YouTuber向け） | [07](07-advice-delivery.md) |

## LLM：フィードバック・アドバイス生成（Claude API）

自然言語の総合フィードバック（ブリーフ・ユースケース①の「試合全体を通じた総合的なフィードバック」）と
アドバイス文生成はClaude APIに委ねる。**動画そのものはLLMに渡さない。**
CVパイプラインが生成した構造化スタッツだけを入力する（コスト・精度・再現性のため）。

### モデル選定

| 用途 | モデル | 理由 |
|---|---|---|
| 試合総合フィードバック、週次ダイジェスト | `claude-opus-4-8`（$5/$25 per MTok） | 戦術的示唆の質が差別化の核。既定モデル |
| 大量バッチ処理（過去試合の一括再分析など） | 同上 + **Batch API** | 非リアルタイム処理は50%割引 |
| 軽量分類（ユーザー修正コメントの正規化など） | `claude-haiku-4-5`（$1/$5 per MTok） | 高頻度・低難度タスクのみ |

### 呼び出し設計（Python SDK）

- **構造化入力**：イベントストリームをそのまま渡さず、taxonomy集計済みの
  コンパクトなスタッツJSON（下記）に変換して渡す。1試合あたり数千トークンに収まる。
- **構造化出力**：`client.messages.parse()` + pydanticスキーマでフィードバックを
  構造化して受け取る（UI表示・アドバイスエンジンでの再利用のため）。
- **プロンプトキャッシュ**：テニスドメイン知識（セオリー、判定基準の説明、出力方針）を
  system promptに固定し `cache_control: {"type": "ephemeral"}` でキャッシュ。
  ユーザーごとのスタッツはmessages側に置く。
  **効果の見積もりは保守的に**：ephemeralのTTLは5分のため、散発的な単発解析ジョブでは
  ヒットしない。キャッシュ割引は週次ダイジェスト等の連続バッチ処理でのみ原価に織り込み、
  単発ジョブはキャッシュなし単価で計上する（[08](08-operations.md)）。
  また最小キャッシュ対象プレフィックスは4096トークンのため、ドメインプロンプトが
  それ未満だと無言でキャッシュされない点に注意。
- **思考制御**：`thinking={"type": "adaptive"}` + `output_config={"effort": "high"}`。

```python
class MatchFeedback(BaseModel):
    summary: str                    # 試合全体の総括（日本語）
    miss_patterns: list[MissPattern]   # 検出したミス傾向（taxonomyラベル参照）
    tactical_notes: list[str]       # 配球・戦術の示唆
    drills: list[DrillSuggestion]   # 次の練習提案（アドバイスエンジンが使用）
    confidence_caveats: list[str]   # データの信頼度に関する注記

response = client.messages.parse(
    model="claude-opus-4-8",
    max_tokens=16000,
    thinking={"type": "adaptive"},
    system=[{"type": "text", "text": TENNIS_DOMAIN_PROMPT,
             "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": stats_json}],
    output_config={"format": MatchFeedback},   # output_format= は非推奨。正準は output_config
)
feedback = response.parsed_output   # 検証済み MatchFeedback インスタンス
```

### Claude APIへの入力スタッツJSON（例）

```jsonc
{
  "player": {"level_hint": "intermediate", "hand": "right"},
  "match": {"sets": "6-4 3-6", "total_points": 118, "unknown_outcome_points": 9},
  "stats": {
    "by_shot_outcome": {"backhand": {"net": 11, "out": 6, "winner": 2}, "...": {}},
    "pressure_split": {"unforced_errors": 21, "forced_errors": 12},
    "serve": {"fault_rate": 0.38},   // 1st/2nd識別（first_in_pct, double_faults）はserve_number軸のv2昇格後
    "rally_length_histogram": {"1-4": 61, "5-8": 35, "9+": 22},  // バケットはadvice-rulesの参照と同一定義

    "trend_vs_last_5_matches": {"backhand_unforced_rate": "+0.08"}
  },
  "confidence": {"overall": 0.81, "notes": ["9ポイントが未分類"]}
}
```

- `confidence` を必ず渡し、system promptで「低信頼データから断定しない」よう指示する。
  `confidence_caveats` として出力にも反映させる（誠実さがコーチング製品の信頼の核）。

## 外部連携まとめ（ブリーフ論点4への回答）

| 領域 | 選定 |
|---|---|
| 姿勢推定 | MediaPipe Pose（＋精度が必要な再解析にMMPose） |
| 物体検出・追跡 | RT-DETR/YOLOX + ByteTrack + TrackNet系 |
| 動画処理 | FFmpeg |
| ホスティング・ストレージ | コンテナ（GPUワーカー分離）+ Cloudflare R2/S3 + CDN |
| 通知・共有 | LINE Messaging API / YouTube Data API（限定公開） |
| 自然言語生成 | Claude API（`claude-opus-4-8`、Batch API、プロンプトキャッシュ） |
