# 10. Phase 0 実装計画（Sonnet向け実装仕様）

対象：[01](01-mvp-scope.md) の Phase 0（編集自動化MVP）のみ。
Phase 1以降の布石は**実装しない**（yagni）。ただし以下の3点だけは例外として最初から入れる
（後からの変更がスキーマ移行になるため）：
イベントストリーム形式（[02](02-architecture.md)）、**認証・通知のチャネル抽象**、
**しきい値のYAML外出し**（不変原則2）。

## リポジトリ構成（モノレポ）

```
tennis-analyzer/
├── backend/            # FastAPI + Celery（CPU系: API、FFmpeg、通知）
│   ├── app/
│   │   ├── api/        # ルーター（uploads, matches, segments, share, auth）
│   │   ├── models/     # SQLAlchemy + Alembic
│   │   ├── jobs/       # Celeryタスク定義（オーケストレーションのみ）
│   │   ├── editing/    # FFmpegコマンド生成・実行
│   │   ├── channels/   # 通知アダプタ（line / email / noop。インターフェース固定）
│   │   └── services/   # R2、署名URL
│   └── tests/
├── cv-worker/          # GPU系Celeryワーカー（別コンテナ・別キュー）
│   ├── ingest.py       # 正規化（HEVC/HDR→H.264/SDR、回転、CFRプロキシ）
│   ├── stages/         # stage1_court.py ... stage4_segments.py（ステージ独立）
│   ├── preflight.py
│   └── tests/
├── frontend/           # Next.js PWA
├── config/
│   ├── taxonomy.v1.yaml        # Phase 0では未使用
│   ├── advice-rules.v1.yaml    # Phase 0では未使用
│   └── segmentation.v1.yaml    # ★Phase 0で使用（区間判定しきい値。下記）
├── docs/
├── docker-compose.yml  # dev環境（postgres, redis, minio, backend, frontend, cv-worker）
└── golden/             # 正解ラベル（labels/*.json）。動画本体はR2
```

- **backend と cv-worker はキューを分ける**（`queue=cpu` / `queue=gpu`）。
  devでは cv-worker もローカルCPUで動かす。**dev軽量モードの定義**：1fpsサンプリング＋
  最小モデル、精度非保証、パイプライン疎通の確認のみが目的。
- devの疑似R2は MinIO。本番との差は環境変数のみ。
- `config/segmentation.v1.yaml`：活動量しきい値・ヒステリシス幅・平滑化窓・
  前後バッファ（開始-2.0s / 終了+1.5s）を外出し。**Phase 0であってもしきい値の
  コード内定数は不変原則2違反**なのでここに置く。

## DBスキーマ（Phase 0）

```sql
users           (id, display_name, email, created_at)
auth_providers  (id, user_id FK, provider, provider_user_id, created_at,
                 UNIQUE(provider, provider_user_id))
                -- provider: line | email_magic （LINEをusersに直接持たせない。
                --  海外展開時のチャネル差し替えをスキーマ変更なしにする）
uploads         (id, user_id FK, r2_key, r2_upload_id, status, total_size,
                 parts JSONB, expires_at, created_at)
                -- status: in_progress | completed | aborted | expired
                -- 中断・放置はexpires_at（48h）でTTL掃除ジョブが R2 AbortMultipartUpload
matches         (id, user_id FK, upload_id FK, title, status, failure_reason,
                 preflight_report JSONB, recorded_at, created_at)
                -- status: queued | preflight | analyzing | editing | done | failed
                -- （アップロード中の状態は uploads が持つ。matchesはupload完了後に作成）
                -- failure_reason: {code, message} code: court_not_detected は使わない
                --  （縮退モードで続行するため。analyze_error | edit_error | input_invalid 等）
video_assets    (id, match_id FK, kind, generation, r2_key, duration_s, meta JSONB, created_at)
                -- kind: original | normalized | edited | hls | thumbnail
                -- generation: recut毎に+1。「現行版」= kindごとの最大generation。
                --  旧世代は新世代の生成成功後に削除。Phase 1で kind=highlight を追加
analysis_jobs   (id, match_id FK, stage, status, attempt, progress, error,
                 metrics JSONB, started_at, finished_at,
                 UNIQUE(match_id, stage, attempt))
                -- stage: ingest | preflight | analyze | edit
                -- metrics 必須キー: {wall_seconds, gpu_seconds, gpu_stage_breakdown,
                --   gpu_unit_price_jpy_per_h(環境変数から記録), cost_estimate_jpy}
event_streams   (id, match_id FK, version, payload JSONB, created_at)
                -- CV出力のイミュータブルなスナップショット。再解析で version+1。
                -- 作成後は更新しない。Phase 0 の payload 必須キー:
                --   video / court(検出できた場合) / points[].clip / confidence
segments        (id, match_id FK, revision, op, base_segment_id, index,
                 start_s, end_s, source, created_at)
                -- source: auto | user。op: add | remove | adjust
                -- auto行は event_streams から初期化（revision=0, op=add）。
                -- 有効区間 = revision昇順に user の op を auto集合に適用した結果。
                -- 編集ジョブは常に「有効区間」だけを読む（真実源はsegments。
                --  event_streamsは更新しない）
share_links     (id, match_id FK, token UNIQUE, revoked, created_at)
                -- token: secrets.token_urlsafe(32)。matchあたり有効リンク1本
                --  （再発行で旧行を revoked=true）。有効期限なし（revokeのみ）
sessions        -- DBに持たない。Redisにserver-side session（30日）
```

- ユーザー修正の履歴保持（auto行を消さない）は設計原則（修正=学習データ）。
- Phase 1 で `Tournament`（matchesの親）とコーチ閲覧権限を追加予定 —
  **Phase 0ではテーブルを作らない**が、matches に nullable な `tournament_id` を
  置くことは禁止しない（マイグレーション1本で済むため布石も不要）。

## API契約

共通事項：

- エラー応答は全エンドポイント共通で `{"error": {"code": string, "message": string, "detail"?: any}}`。
  バリデーション422 / 認証切れ401 / 他人のリソース**404**（403は使わない：存在の秘匿） /
  競合409 / サイズ超過413。
- 認証：`/api/auth/*` と `GET /s/{token}` 系以外は**全てセッション必須**。
  M1〜M4 期間は「devユーザー自動作成＋固定セッション」で動かす（下記マイルストーン）。
- レート制限はPhase 0では入れない（yagni。abuse検知はアップロード数/日の上限のみ：10本/日）。

### アップロード（マルチパート・中断再開対応）

モバイル回線で数GBを送る前提のため、**再開可能性が最重要**（[09](09-go-to-market.md) のファネル）：

| メソッド/パス | 内容 |
|---|---|
| `POST /api/uploads` | 開始。`{filename, total_size, content_type}` → `{upload_id, part_size}`。上限 **8GB**（1080p/30fps 2時間相当。[08](08-operations.md) の原本4〜6GB想定を包含）、超過は413。`video/*` 以外は422 |
| `POST /api/uploads/{id}/parts` | `{part_numbers: [..]}` → パートごとのpresigned URL発行（都度・複数可。再開時は未完了パートのみ要求） |
| `GET /api/uploads/{id}` | 進捗照会。`{status, completed_parts: [..]}`（クライアント再起動後の再開に使う） |
| `POST /api/uploads/{id}/complete` | 全パートのETagを受けて R2 CompleteMultipartUpload を**サーバー側で**実行 |
| `DELETE /api/uploads/{id}` | 中止（AbortMultipartUpload） |

- R2/MinIOのCORS設定（PUT許可・ETag公開）はdocker-compose / IaCに含める（実装タスク）。
- フロントは Wi-Fi待ちキュー＋バックグラウンド再開を必須要件とする
  （iOS Safariのタブ切替・画面ロックでの中断が常態。localStorage に upload_id と
  完了パートを永続化し、再開時は `GET /api/uploads/{id}` と突き合わせる）。

### 試合・区間・共有

| メソッド/パス | 内容 |
|---|---|
| `POST /api/matches` | `{upload_id, title}`。uploads.status=completed が前提（違えば409）→ ingestジョブ投入 |
| `GET /api/matches` / `GET /api/matches/{id}` | 一覧・詳細。詳細は `{status, failure_reason, preflight_report, assets(現行世代のみ), progress: {stage, pct}}`。progressは analysis_jobs の最新attemptから stage重み（ingest 20/preflight 10/analyze 50/edit 20）で合成 |
| `GET /api/matches/{id}/segments` | `{revision, effective: [{start_s, end_s}], raw: [...]}`（有効区間は計算済みで返す） |
| `PATCH /api/matches/{id}/segments` | ボディ `{base_revision, ops: [{op, base_segment_id?, start_s?, end_s?}]}`。`base_revision` が現在値と不一致なら**409**（楽観ロック）。適用後 revision+1 |
| `POST /api/matches/{id}/recut` | editジョブのみ再実行。editing中の再投入は409。CVは再実行しない |
| `POST /api/matches/{id}/share` | 共有リンク発行/再発行 → `{url}`（旧tokenはrevoked） |
| `DELETE /api/matches/{id}/share` | 共有停止（revoked=true） |
| `GET /api/share/{token}/playback` | **視聴ページが再生情報を取得するAPI**（認証不要、revoked=404）。HLSは「バックエンドがその場で署名済みセグメントURL入りの m3u8 を生成して返す」方式：`{playlist_url: "/api/share/{token}/playlist.m3u8", thumbnail_url}` |
| `GET /api/share/{token}/playlist.m3u8` | R2上のm3u8を読み、各セグメントURIを署名付きURL（有効1h）に書き換えて返す。**S3署名URLの7日上限を「リンクの寿命」と混同しない**：リンクの寿命はtoken（revokeまで有効）、署名は再生のたびに短命発行 |

### 認証

| メソッド/パス | 内容 |
|---|---|
| `POST /api/auth/line` | LINE Login **v2.1 authorization code flow**（LIFFは使わない。PWAの通常ブラウザ文脈で動かす）。IDトークンはチャネルIDで audience 検証 → auth_providers に upsert → Redisセッション発行。Cookie: HttpOnly + Secure + SameSite=Lax、30日 |
| `POST /api/auth/logout` | セッション破棄 |

- 登録フローで**メールアドレスを必ず取得**（LINEのメール取得許諾 or 手入力。[07](07-advice-delivery.md)）。
- **PWA standalone（ホーム追加）モードでのOAuthリダイレクト＋Cookie持続の動作確認をM5の完了条件に含める**（iOSの既知の落とし穴）。
- 通知は `channels/` のアダプタ経由でのみ送る。Phase 0 実装は line / email / noop の3つ。
  LINE Login（認証）と Messaging API（push）は**別チャネル**であり、友だち追加していない
  ユーザーにpushは送れない → ログイン後に友だち追加を導線化し、未友だちはemailへフォールバック、
  それも無ければアプリ内表示のみ。

## ジョブフロー

```
POST /matches
  → [gpu] ingest（ffprobe判定 → 回転正規化・HEVC/HDR→H.264/SDR・CFRプロキシ生成。[02](02-architecture.md)）
      ※ 縦動画: preflight warn 扱いで続行。VFR: CV入力のみCFR化
  → [gpu] preflight（正規化済み動画の先頭60秒・2fpsサンプル。[03](03-recording-guidelines.md)）
      ├─ コート検出OK → [gpu] analyze（stage1-4 → event_streams v1 + segments revision0）
      └─ コート検出NG → **縮退モード**：stage2/4のみ（活動量ベース区間分割）で続行。
          preflight_report に degraded=true を記録し、UIとLINE通知で撮影ガイドを案内
      （その他の警告 — 画角・手ブレ・輝度・低解像度 — は全て記録の上で自動続行。
        ユーザー確認は挟まない）
  → [cpu] edit（有効区間をキーフレームに外側スナップして -c copy 連結 → HLS生成 →
      thumbnail生成（editジョブ末尾）→ 単一レンディション・6秒セグメント・オーバーレイなし）
  → status=done、channels経由で完了通知
POST /recut → [cpu] edit のみ再実行（video_assets.generation+1）
```

- `preflight_report` のスキーマ：`{checks: {court: {result: ok|warn|fail, value, message},
  coverage: {...}, stability: {...}, brightness: {...}, resolution: {...}},
  degraded: bool, sampled_range_s: [0, 60]}`。matches.preflight_report に保存。

### 冪等性・リトライ（実装要件）

- 全ジョブは match_id + 入力アセット世代で決まり、再実行しても行を重複させない
  （event_streams はversion+1、segments/assetsはgeneration方式、jobs はattempt+1）。
- **失敗の分類**：恒久失敗（入力不正・コーデック非対応）は即 status=failed＋failure_reason。
  一時失敗（OOM・ネットワーク・スポット中断）のみ指数バックオフで最大3回。
  3回失敗で failed＋ユーザー通知＋管理用再投入コマンド（`make requeue MATCH=..`）。
- **ワーカーごと死ぬケース**（スポットGPUのプリエンプション）に備え、Celeryは
  `acks_late=True` + `task_reject_on_worker_lost=True`。Redisブローカーの
  `visibility_timeout` はジョブ最長時間（60分）×2 に設定（デフォルト1hのままにしない）。
- ステージ間チェックポイント：各ステージ出力を保存済みなら再実行時にスキップ
  （stage単位の再開。30分ジョブの頭からやり直しをしない）。

## CVパイプライン Phase 0 実装指針

| ステージ | 実装 | Phase 0 での割り切り |
|---|---|---|
| ingest | ffprobe + ffmpeg（NVENC） | 判定分岐（HEVC/HDR/VFR/回転/縦）を網羅するテストを先に書く |
| 1 コート検出 | 白線検出＋RANSACホモグラフィ。**コート寸法は court-spec.yaml から読む**（[05](05-tech-stack.md)） | コート種別分類は unknown 固定でよい。検出失敗＝縮退モードで続行（failにしない） |
| 2 選手検出・追跡 | RT-DETR/YOLOX（人物）＋ByteTrack | 人数は可変（ダブルス4名対応）。選手同定は不要、コート内の活動量が取れれば十分 |
| 3 ボール検出 | TrackNet系 | 「ボールが動いているか」の活動量シグナルが取れれば十分。軌道復元はPhase 1 |
| 4 ポイント区間分割 | 活動量時系列をしきい値＋ヒステリシスで2値化 | しきい値・平滑化・バッファは `config/segmentation.v1.yaml` から読む。ML分類器にしない |

### ステージ間の入出力契約（フィールド名レベルで固定）

```jsonc
// stage2 出力（stage3も同形式で ball_motion を出す）
{"fps_sampled": 5, "per_frame": [{"t": 0.2, "n_persons": 4, "motion_energy": 0.31}],
 "confidence": 0.9}
// stage4 出力（= event_streams.points の素）
{"segments": [{"start_s": 613.2, "end_s": 641.8, "confidence": 0.84}],
 "params_version": "segmentation.v1"}
```

- 各ステージは `stage_input.json → stage_output.json` の独立CLIとしても実行可能にする
  （ゴールデンセット回帰・デバッグ用。設計原則3）。
- 区間判定は**プレー区間を削らない方向に倒す**（適合率優先。[01](01-mvp-scope.md)）。

## ゴールデンセット（調達と判定を仕様化）

- **調達はM1期間中のタスク**：ユーザー自身（開発者）が3条件（オムニ/ハード/画角悪）で
  実際に撮影する。M3開始時に3本無ければM3は開始できない（クリティカルパス）。
  Phase 0完了までに10本へ拡充（知人サークルの協力。同意書テンプレートを用意）。
- 正解ラベル：`golden/labels/{id}.json` = `{"segments": [{"start_s", "end_s"}], "notes"}`。
- 合否判定（`make golden` で実行）：正解区間とのIoU ≥ 0.8（境界許容±1.0s）を一致とし、
  適合率 ≥ 90% / 再現率 ≥ 80% を下回ったらfail（リリースゲート。[08](08-operations.md)）。

## フロントエンド（Phase 0 の画面は4つだけ）

1. **アップロード画面** — Wi-Fi待ちキュー・中断再開・進捗（uploads API準拠）
2. **試合詳細** — 解析進捗 / 完了後はプレーヤー + 区間タイムライン + 共有ボタン
3. **区間修正UI** — タイムライン上で区間の追加・削除・端点ドラッグ → PATCH（base_revision付き）→ recut
4. **共有視聴ページ**（`/s/{token}`） — playback API経由のHLS再生 + 登録導線
   （クレーム導線はPhase 2。ボタンだけ「準備中」で置くこともしない — yagni）

- 動画再生は hls.js（ingestでH.264化済みなので全ブラウザ再生可能）。
- PWA要件は「ホーム追加・アップロード安定」まで。オフライン対応はしない。

## 実装順序（縦切りマイルストーン）

| M | 内容 | 完了条件（動くもの） |
|---|---|---|
| M1 | compose + FastAPI骨格 + devユーザー自動作成 + uploads API（再開含む）+ MinIO | 中断→再開込みでアップロード完遂し uploads/matches 行とR2オブジェクトができる。**ゴールデンセット3本の撮影もここで行う** |
| M2 | ingest（正規化）+ editワーカー + HLS + 視聴ページ。analyzeは**スタブ**（segmentsに固定3区間をsource=autoでINSERT） | 実スマホ動画（HEVC）をアップロード→正規化→（ダミー区間で）編集済みHLSが全ブラウザで再生できる。**E2Eの配管が先、CVは差し替え** |
| M3 | preflight + stage1-4 + 縮退モード（ゴールデンセット3本で `make golden` パス） | 実動画で区間が自動検出されM2の配管に流れる。スタブと同じくsegmentsに書くだけなので差し替えは1点 |
| M4 | 区間修正UI + PATCH（楽観ロック）+ recut（世代管理） | 誤検出をユーザーが直して再編集できる。2タブ同時編集で409が返る |
| M5 | LINEログイン（+メール取得）+ channels（line/email/noop）+ 完了通知 + 共有リンク | 通しのユーザー体験が成立。**PWA standaloneでのログイン動作確認を含む**（Phase 0 完了） |

## 実装時の規約（Sonnetへの申し送り）

- 設計の不変原則4項（CLAUDE.md）を破る実装をしない。迷ったら設計ドキュメントに戻る。
  設計変更が必要になったら**実装せずユーザーに確認**（設計=Fable、実装=Sonnetの分業）。
- 例外・エッジケース処理は省略しない。それ以外の「将来のため」のコードは書かない（yagni-guard）。
- シークレットは環境変数（`.env.example` を整備）。LINEチャネルシークレット・R2キーをコミットしない。
- テスト：backend は compose 内 pytest（CI は GitHub Actions・GPUなし前提。
  cv-worker のテストはdev軽量モード＋10秒フィクスチャ動画で回す）。
  フル動画は `make golden`（ローカル/GPU環境でのみ実行）に分離。
- コート寸法・区間判定しきい値・通知チャネルを**コードにハードコードしない**
  （それぞれ court-spec.yaml / segmentation.v1.yaml / channels アダプタ）。
