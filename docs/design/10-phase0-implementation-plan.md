# 10. Phase 0 実装計画（Sonnet向け実装仕様）

対象：[01](01-mvp-scope.md) の Phase 0（編集自動化MVP）のみ。
Phase 1以降の布石（ルールエンジン、スタッツ、ショット分類）は**実装しない**（yagni）。
ただしイベントストリーム形式（[02](02-architecture.md)）だけは将来互換のスキーマで出力する。

## リポジトリ構成（モノレポ）

```
tennis-analyzer/
├── backend/            # FastAPI + Celery（CPU系: API、FFmpeg、通知）
│   ├── app/
│   │   ├── api/        # ルーター（uploads, matches, segments, share, auth）
│   │   ├── models/     # SQLAlchemy + Alembic
│   │   ├── jobs/       # Celeryタスク定義（オーケストレーションのみ）
│   │   ├── editing/    # FFmpegコマンド生成・実行
│   │   └── services/   # R2、LINE、署名URL
│   └── tests/
├── cv-worker/          # GPU系Celeryワーカー（別コンテナ・別キュー）
│   ├── stages/         # stage1_court.py ... stage4_segments.py（ステージ独立）
│   ├── preflight.py
│   └── tests/          # ゴールデンセット回帰（[08](08-operations.md)）
├── frontend/           # Next.js PWA
├── config/             # taxonomy等（Phase 0では未使用、既存のまま）
├── docs/
├── docker-compose.yml  # dev環境（postgres, redis, minio, backend, frontend）
└── golden/             # ゴールデンセット動画のメタデータ・正解ラベル（動画本体はR2）
```

- **backend と cv-worker はキューを分ける**（`queue=cpu` / `queue=gpu`）。
  devでは cv-worker もローカルCPUで動かす（モデルを軽量設定に切替）。
- devの疑似R2は MinIO。本番との差は環境変数のみ。

## DBスキーマ（Phase 0）

```sql
users          (id, line_user_id UNIQUE, display_name, created_at)
matches        (id, user_id FK, title, status, recorded_at, created_at)
               -- status: uploading | preflight | analyzing | editing | done | failed
video_assets   (id, match_id FK, kind, r2_key, duration_s, meta JSONB, created_at)
               -- kind: original | edited | hls | thumbnail
analysis_jobs  (id, match_id FK, stage, status, progress, error, metrics JSONB,
                started_at, finished_at)
               -- metrics: {gpu_seconds, cost_estimate_jpy, ...} ← 原価計測（[08](08-operations.md)）
event_streams  (id, match_id FK, version, payload JSONB, created_at)
               -- payload: [02](02-architecture.md) の形式。Phase 0 は court/points[].clip のみ
segments       (id, match_id FK, index, start_s, end_s, source, created_at)
               -- source: auto | user  ← 手動修正は行追加（autoを消さない = 学習データ）
share_links    (id, match_id FK, token UNIQUE, revoked, created_at)
```

- `segments` を `event_streams` と別テーブルに持つのは手動修正UIの
  読み書き単位だから。編集動画の再生成は segments を正とする。
- ユーザー修正の履歴保持（auto行を残す）は設計原則（修正=学習データ、[02](02-architecture.md)）。

## API契約

| メソッド/パス | 内容 |
|---|---|
| `POST /api/auth/line` | LINEログイン（IDトークン検証 → セッションCookie発行） |
| `POST /api/uploads` | R2へのpresigned URL発行（マルチパート、最大4GB） |
| `POST /api/matches` | アップロード完了通知 → preflightジョブ投入。`{upload_id, title}` |
| `GET /api/matches` / `GET /api/matches/{id}` | 一覧・詳細（status、preflight_report、assets、進捗） |
| `GET /api/matches/{id}/segments` | 区間リスト（auto+user、有効区間を計算済みで返す） |
| `PATCH /api/matches/{id}/segments` | 手動修正（追加・削除・端点調整）→ `source=user` 行を追加 |
| `POST /api/matches/{id}/recut` | 修正後の再編集ジョブ投入（CVは再実行しない） |
| `POST /api/matches/{id}/share` | 共有リンク発行 → `{url}` |
| `GET /s/{token}` | **認証不要の視聴ページ**（フロントで実装。HLS再生 + 登録導線、[09](09-go-to-market.md)） |

- 進捗はポーリング（`GET /api/matches/{id}` を5秒間隔）。WebSocketは入れない（yagni）。
- 動画・HLSへのアクセスはすべてR2署名付きURL経由。共有ページ用は有効期限長め（7日）で都度再発行。

## ジョブフロー

```
POST /matches
  → [gpu] preflight（先頭60秒: コート検出・画角・固定・明るさ、[03](03-recording-guidelines.md)）
      ├─ コート検出NG → status=failed(理由付き)、撮影ガイドをLINEで返す
      └─ OK/警告 → [gpu] analyze（stage1-4 → event_streams + segments(auto)）
            → [cpu] edit（FFmpeg: クリップ連結、-c copy優先、HLS生成）
                → status=done、LINE通知「編集済み動画ができました」
POST /recut → [cpu] edit のみ再実行（segmentsの最新有効区間から）
```

- **全ジョブ冪等**：入力は match_id + 入力アセットのバージョンで決まり、
  再実行しても行を重複させない（UPSERT / 世代番号）。リトライはCeleryの自動リトライ（3回）。
- 各ジョブ完了時に `metrics`（GPU秒・処理時間・推定原価）を記録（[08](08-operations.md) の初日計測）。

## CVパイプライン Phase 0 実装指針

| ステージ | 実装 | Phase 0 での手抜きライン |
|---|---|---|
| 1 コート検出 | 白線検出＋RANSACホモグラフィ（自前薄実装、[05](05-tech-stack.md)） | コート種別分類は `unknown` 固定でよい（オムニ対応の学習は後続） |
| 2 選手検出・追跡 | RT-DETR/YOLOX（人物クラスのみ）＋ByteTrack | 選手同定（自分/相手）は不要。人数・活動量が取れれば十分 |
| 3 ボール検出 | TrackNet系 | 軌道の完全復元は不要。**「ボールが動いているか」が取れれば十分** |
| 4 ポイント区間分割 | 選手・ボール活動量の時系列をしきい値＋平滑化で2値化 | ML分類器にしない。ルールベース＋ヒステリシスで開始 |

- 各ステージは `stage_input.json → stage_output.json`（＋信頼度）の独立CLIとしても実行可能にする
  （ゴールデンセット回帰とデバッグのため。設計原則3）。
- 区間判定の方針：**プレー区間を削らない方向に倒す**（適合率優先、[01](01-mvp-scope.md) の成功指標）。
  境界には前後バッファ（開始-2s / 終了+1.5s）を付ける。

## フロントエンド（Phase 0 の画面は4つだけ）

1. **アップロード画面** — ファイル選択 → 直接R2へマルチパートPUT → 進捗表示
2. **試合詳細** — 解析進捗 / 完了後はプレーヤー + 区間タイムライン + 共有ボタン
3. **区間修正UI** — タイムライン上で区間の追加・削除・端点ドラッグ → recut
4. **共有視聴ページ**（`/s/{token}`） — HLS再生 + 「自分の試合も解析する」導線

- PWA要件は「ホーム追加・スマホでのアップロード安定」まで。オフライン対応はしない。
- 動画再生は hls.js。タイムラインUIは自前の薄い実装（ライブラリ依存を増やさない）。

## 実装順序（縦切りマイルストーン）

| M | 内容 | 完了条件（動くもの） |
|---|---|---|
| M1 | docker-compose + FastAPI骨格 + DB + R2(MinIO)アップロード | 動画をアップロードして matches 行とR2オブジェクトができる |
| M2 | FFmpeg編集ワーカー（**固定のダミー区間**でカット）+ HLS + 視聴ページ | アップロード→（ダミー）編集済み動画が再生できる。**E2Eの骨格が先** |
| M3 | CVステージ1-4 + preflight（ゴールデンセット3本で検証） | 実動画で区間が自動検出され、M2に流れる |
| M4 | 区間修正UI + recut | 誤検出をユーザーが直して再編集できる |
| M5 | LINEログイン + 完了通知 + 共有リンク | 通しのユーザー体験が成立（Phase 0 完了） |

- **M2 を CV より先に**やる：パイプラインの配管（ジョブ・ストレージ・配信）を
  ダミーデータで先に通し、CVは「差し替え」にする。精度調整で配管が待たされない。
- ゴールデンセットは M3 開始時に最低3本（オムニ/ハード/画角悪）を用意し、
  `golden/` に正解区間ラベルを置く。

## 実装時の規約（Sonnetへの申し送り）

- 設計の不変原則4項（CLAUDE.md）を破る実装をしない。迷ったら設計ドキュメントに戻る。
  設計変更が必要になったら**実装せずユーザーに確認**（設計=Fable、実装=Sonnetの分業）。
- 例外・エッジケース処理は省略しない。それ以外の「将来のため」のコードは書かない（yagni-guard）。
- シークレットは環境変数（`.env.example` を整備）。LINEチャネルシークレット・R2キーをコミットしない。
- テスト：backend はエンドポイント単位の統合テスト（testcontainers または compose 内 pytest）、
  cv-worker はゴールデンセット回帰スクリプトを CI 相当として `make golden` で実行可能に。
- 動画を扱うテストは重いので、**10秒程度の小片動画をフィクスチャ化**して単体を回し、
  フル動画はゴールデンセット回帰でのみ使う。
