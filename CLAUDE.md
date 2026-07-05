# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの現状

テニス動画分析アプリの**設計フェーズ**のリポジトリ。現時点でアプリケーションコードは無く、
設計ドキュメント（`docs/design/`）と設定ファイル（`config/`）のみで構成される。
ビルド・テストコマンドはまだ存在しない。実装着手時は `docs/design/01-mvp-scope.md` の
フェーズ計画（Phase 0 = 編集自動化MVP）に従うこと。

## ドキュメントの読み順

`docs/design/00-overview.md` が意思決定サマリ。個別論点は 01〜07 に分かれており、
番号はブリーフの論点番号にほぼ対応する。設計変更時は 00 のサマリ表も更新すること。

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
  labelsは上から順に最初のマッチを採用、ルールには `default` が必須。
- `advice-rules.v1.yaml` — アドバイス発火条件とテンプレート。「何を言うか」はルール、
  「どう言うか」はClaude APIという分業。
- 両ファイルともバージョン付きリソースとして扱い、破壊的変更は新バージョンファイルを追加する。

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
