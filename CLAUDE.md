# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの現状

テニス動画分析アプリの**設計フェーズ**のリポジトリ。現時点でアプリケーションコードは無く、
設計ドキュメント（`docs/design/`）と設定ファイル（`config/`）のみで構成される。
ビルド・テストコマンドはまだ存在しない。実装着手時は `docs/design/01-mvp-scope.md` の
フェーズ計画（Phase 0 = 編集自動化MVP）に従うこと。

## セッション運用ルール

- **モデルの分業**：設計（アーキテクチャ・ドキュメント・意思決定）は `claude-fable-5`、
  実装（コード作成）は Sonnet で行う。現在のモデルが役割と合わない場合はユーザーに
  モデル切替（`/model`）を促すこと。
- **claude-skills リポジトリの運用ルールを適用する**（`ryotaroh180105/claude-skills` の
  CLAUDE.md 参照。セッションに追加されていなければ `add_repo` で取り込む）：
  - token-saver：前置き・反復説明なし、箇条書き優先
  - yagni-guard：依頼にない抽象化・依存を追加しない（設計にも適用）
  - Web/X の調査は hermes-relay 経由（Claude 自身の WebSearch は使わない）

## ドキュメントの読み順

`docs/design/00-overview.md` が意思決定サマリ。個別論点は 01〜11 に分かれており、
01〜07 はブリーフの論点番号にほぼ対応、08 が導入・保守・運用、09 がマーケ・差別化・拡張戦略、
**10 が Phase 0 実装仕様（実装セッションはまずこれを読む）**、11 がUI設計。
設計変更時は 00 のサマリ表も更新すること。

## 設計上の不変原則（変更にはユーザー合意が必要）

1. **スマホ1台撮影が前提** — 全解析結果に信頼度スコアを付与し、低信頼は `unknown` として
   ユーザー修正に委ねる。「誤った断定より未分類」を優先する。
2. **粒度のハードコード禁止** — ミス分類軸・判定しきい値・アドバイス発火条件は
   `config/*.yaml` に外出しする。カテゴリ追加はYAML編集のみで完結させ、コード側は
   YAMLを解釈するルールエンジンに徹する。
3. **CVパイプラインはステージ独立** — 各ステージの中間出力を保存し、下流のみの再実行
   （taxonomy変更でミス分類だけ再計算等）を可能に保つ。
4. **動画をLLMに渡さない** — Claude APIへの入力は集計済み構造化スタッツJSONのみ。

## 設定ファイル（config/）

- `taxonomy.v1.yaml` — ミス分類の軸（dimensions）・判定式（rules）・しきい値（thresholds）・
  ラベル（labels）。`when` 式はサンドボックス評価器で実行する前提（`eval` 禁止）。
  判定式が参照できるのはイベントストリームに実在するフィールドのみ（存在しない参照は
  スキーマ検証で拒否）。labelsは上から順に最初のマッチを採用し catch-all（`match: {}`）必須、
  ルールには `default` が必須。ラベルはロケールキー型（`label: {ja: ...}`）。
- `advice-rules.v1.yaml` — アドバイス発火条件とテンプレート。「何を言うか」はルール、
  「どう言うか」はClaude APIという分業。DSL定義はファイル冒頭コメントが正。
- `segmentation.v1.yaml`（Phase 0で新設） — 区間判定しきい値。しきい値のコード内定数は禁止。
- 全ファイルともバージョン付きリソースとして扱い、破壊的変更は新バージョンファイルを追加する。
- コート寸法・ライン定義は `court-spec.yaml` に外出しする（コードへのハードコード禁止。
  他ラケットスポーツ展開時の改修範囲を限定するため）。

## 技術選定の要点（docs/design/05-tech-stack.md）

- CV: RT-DETR/YOLOX + ByteTrack + TrackNet系 + MediaPipe Pose（Ultralyticsは
  AGPLライセンスのため採用時は要確認）
- 動画: FFmpeg（`-c copy` 優先、キーフレームスナップ）、HLS配信、Cloudflare R2/S3
- バックエンド: Python / FastAPI + Celery + Redis + PostgreSQL（イベントストリームはJSONB）
- LLM: Claude API `claude-opus-4-8`（`messages.parse()` + pydantic構造化出力、
  ドメインプロンプトはプロンプトキャッシュ、週次ダイジェストはBatch API）
- 通知: LINE Messaging API

## 権利面の制約（docs/design/06-pro-reference-data.md）

プロ選手の放送映像・YouTube映像からの骨格抽出、および特定選手名を使った比較機能は
**実装しない**と決定済み。フォーム比較はバイオメカ文献レンジのYAMLパラメータ化と
契約コーチの撮り下ろし映像で行う。
