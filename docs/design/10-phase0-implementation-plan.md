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
├── cv-worker/          # GPU系ワーカー（別コンテナ）
│   ├── precheck.py     # CPU実行（backend側cpuキューから呼ぶ薄いラッパも可）
│   ├── ingest.py       # 正規化（HEVC/HDR→H.264/SDR、回転、CFRプロキシ、GOP 2s）
│   ├── stages/         # stage1_court.py ... stage4_segments.py（ステージ独立）
│   └── tests/
├── dispatcher/         # GPUジョブディスパッチャ（下記）
├── frontend/           # Next.js PWA
├── config/
│   ├── taxonomy.v1.yaml        # Phase 0では未使用
│   ├── advice-rules.v1.yaml    # Phase 0では未使用
│   ├── segmentation.v1.yaml    # ★Phase 0で使用（区間判定・サンプリング・縮退パラメータ）
│   └── court-spec.v1.yaml      # ★Phase 0で使用（コート寸法・ライン定義）
├── docs/
├── docker-compose.yml  # dev環境（postgres, redis, minio, backend, frontend, cv-worker）
└── golden/             # 正解ラベル（labels/*.json）。動画本体はR2
```

- **GPUジョブディスパッチャ**：CeleryワーカーモデルとサーバーレスGPU（RunPod/Modal）は
  素直に接続できないため、接着コンポーネントを明示的に作る。実装：cpuキュー上の
  ディスパッチャタスクがプロバイダAPIでコンテナを起動し、ジョブ引数を渡して完了を待つ
  （＝Celery gpuキューは廃止。「キュー長連動の並列度」はディスパッチャの同時起動数制御で実現）。
  コンテナイメージ（CUDA＋モデル数GB）は**プロバイダのイメージキャッシュを効かせる**
  （未キャッシュ時のpullはコールドスタート1〜2分の想定を超える）。M2の完了条件に含める。
- devでは cv-worker をローカルCPUで動かす。**dev軽量モードの定義**：1fpsサンプリング＋
  最小モデル、`ENCODER=libx264`、精度非保証、パイプライン疎通の確認のみが目的。
- devの疑似R2は MinIO。本番との差は環境変数のみ。
- `config/segmentation.v1.yaml`：サンプリング（基準5Hz＋隣接3フレームバースト）・活動量合成の
  重み・ヒステリシス・バッファ・**縮退モード用パラメータセット**まで実ファイルに定義済み。
  **Phase 0であってもしきい値のコード内定数は不変原則2違反**。

## DBスキーマ（Phase 0）

```sql
users           (id, display_name, email, locale, created_at)
                -- email: NULL可（devユーザー・取得前）。locale: 既定 'ja'。
                --  通知・LLM生成・UIの言語はこのカラムから引く（i18nの配線。設計方針7）
auth_providers  (id, user_id FK, provider, provider_user_id, created_at,
                 UNIQUE(provider, provider_user_id))
                -- provider: line | email_magic （LINEをusersに直接持たせない。
                --  海外展開時のチャネル差し替えをスキーマ変更なしにする）
uploads         (id, user_id FK, r2_key, r2_upload_id, status, total_size,
                 expires_at, created_at)
                -- status: in_progress | completed | aborted | expired
                -- in_progress はexpires_at（48h）でTTL掃除ジョブが R2 AbortMultipartUpload。
                -- completed のまま match 未作成のものは7日で R2 オブジェクトごと削除。
                -- 1 upload = 1 match（使用済み upload_id での POST /matches は409）。
                -- パート進捗はDBに持たない（R2 ListParts が正）
matches         (id, user_id FK, upload_id FK UNIQUE, title, status, failure_reason,
                 preflight_report JSONB, recorded_at, stage_results_r2_key, created_at)
                -- status: queued | prechecking | ingesting | analyzing | editing | done | failed
                --  （analysis_jobs.stage との対応: precheck→prechecking, ingest→ingesting,
                --    analyze→analyzing, edit→editing。queuedは各stageの待機中）
                -- recorded_at: 動画メタデータの撮影日時。無ければ created_at で初期化
                -- failure_reason: {code, message} code: input_invalid | analyze_error |
                --  edit_error | retry_exhausted（court_not_detected は使わない — 縮退続行のため）
                -- stage_results_r2_key: stage1-3出力（重い部分）をgzip JSONで保存したR2キー。
                --  設定済みならanalyzeジョブのリトライ時にstage1-3を再実行せずstage4-5のみ
                --  再実行する（ステージ間チェックポイント、不変原則3）
video_assets    (id, match_id FK, kind, generation, r2_key, duration_s, meta JSONB, created_at)
                -- kind: original | normalized | edited | hls | thumbnail
                -- original 行は POST /matches 時に uploads.r2_key を参照して作成（コピーしない）
                -- generation: recut毎に+1。「現行版」= kindごとの最大generation。
                --  旧世代は新世代の生成成功後に削除。Phase 1で kind=highlight を追加
analysis_jobs   (id, match_id FK, stage, status, attempt, progress, error,
                 metrics JSONB, started_at, finished_at,
                 UNIQUE(match_id, stage, attempt))
                -- stage: precheck | ingest | analyze | edit
                -- metrics 必須キー: {wall_seconds, gpu_seconds,
                --   breakdown: {download_s, encode_s, stage1_s..stage4_s, upload_s},
                --   unit_price: {amount, currency, per: "hour"},   -- 通貨をキー名に焼き込まない
                --   cost_estimate: {amount, currency}}             -- （設計方針7）
event_streams   (id, match_id FK, version, payload JSONB, created_at)
                -- CV出力のイミュータブルなスナップショット。再解析で version+1。
                -- 作成後は更新しない。Phase 0 の payload 必須キー:
                --   video / court(検出できた場合) / points[].clip / confidence
segments        (id, match_id FK, revision, op, base_segment_id, start_s, end_s,
                 source, created_at)
                -- source: auto | user。op: add | remove | adjust
                -- auto行は event_streams から初期化（revision=0, op=add）。
                -- base_segment_id は auto行 または それ以前の user add行 の id を指せる
                --  （ユーザーが自分で追加した区間の削除・調整を可能にする）。
                -- 有効区間 = revision昇順に全opを適用した結果。編集ジョブは常に有効区間のみ読む
                --  （真実源はsegments。event_streamsは更新しない）。
                -- op別必須フィールド: add={start_s,end_s} / remove={base_segment_id} /
                --  adjust={base_segment_id, start_s, end_s}
                -- 検証: start_s < end_s、0 ≤ 値 ≤ 動画長、違反は422
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
- レート制限はPhase 0では入れない（yagni。abuse検知はアップロード数/日の上限のみ：10本/日。
  超過は **429** + `{"error": {"code": "rate_limited"}}`）。

### アップロード（マルチパート・中断再開対応）

モバイル回線で数GBを送る前提のため、**再開可能性が最重要**（[09](09-go-to-market.md) のファネル）：

| メソッド/パス | 内容 |
|---|---|
| `POST /api/uploads` | 開始。`{filename, total_size, content_type}` → `{upload_id, part_size}`。上限は**サイズ16GB かつ 2.5時間**の二軸（AndroidのH.264録画は1080p30で2時間14〜18GBになり得るため。コーデック効率の案内は撮影ガイドに）。超過は413。`video/*` 以外は422 |
| `POST /api/uploads/{id}/parts` | `{part_numbers: [..]}` → パートごとのpresigned URL発行（都度・複数可。再開時は未完了パートのみ要求） |
| `GET /api/uploads/{id}` | 進捗照会。R2 ListParts を照会し `{status, completed_parts: [{part_number}]}` を返す（クライアント再起動後の再開に使う。**ETagはクライアントに持たせない**） |
| `POST /api/uploads/{id}/complete` | ボディなし。**サーバーが R2 ListParts でパート一覧・ETagを取得して** CompleteMultipartUpload を実行（クライアントのETag紛失＝再開不能、を構造的に排除） |
| `DELETE /api/uploads/{id}` | 中止（AbortMultipartUpload） |

- R2/MinIOのCORS設定（PUT許可・ETag公開）はdocker-compose / IaCに含める（実装タスク）。
- フロントは Wi-Fi待ちキュー＋バックグラウンド再開を必須要件とする
  （iOS Safariのタブ切替・画面ロックでの中断が常態。localStorage に upload_id と
  完了パートを永続化し、再開時は `GET /api/uploads/{id}` と突き合わせる）。

### 試合・区間・共有

| メソッド/パス | 内容 |
|---|---|
| `POST /api/matches` | `{upload_id, title}`。uploads.status=completed かつ未使用が前提（違えば409）→ precheckジョブ投入 |
| `GET /api/matches` / `GET /api/matches/{id}` | 一覧・詳細。詳細は `{status, failure_reason, preflight_report, assets(現行世代のみ), progress: {stage, pct}}`。progressは analysis_jobs の最新attemptから stage重み（precheck 10/ingest 25/analyze 45/edit 20）で合成 |
| `GET /api/matches/{id}/segments` | `{revision, effective: [{start_s, end_s}], raw: [{id, revision, op, base_segment_id, start_s, end_s, source}]}` |
| `PATCH /api/matches/{id}/segments` | ボディ `{base_revision, ops: [{op, base_segment_id?, start_s?, end_s?}]}`。`base_revision` 不一致は**409**（楽観ロック）。適用後 revision+1。**status=done のときのみ受付**（解析・編集中は409） |
| `POST /api/matches/{id}/recut` | editジョブのみ再実行。**status=done のときのみ受付**（それ以外409）。CVは再実行しない |
| `POST /api/matches/{id}/share` | 共有リンク発行/再発行 → `{url}`（旧tokenはrevoked） |
| `DELETE /api/matches/{id}/share` | 共有停止（revoked=true） |
| `GET /api/share/{token}/playback` | **視聴ページが再生情報を取得するAPI**（認証不要、revoked=404）。HLSは「バックエンドがその場で署名済みセグメントURL入りの m3u8 を生成して返す」方式：`{playlist_url: "/api/share/{token}/playlist.m3u8", thumbnail_url}` |
| `GET /api/share/{token}/playlist.m3u8` | R2上のm3u8を読み、各セグメントURIを署名付きURL（**有効12h** — VODのm3u8は再生開始時に一度しか取得されないため、一時停止・離席で1hを跨ぐと再生が死ぬ。動画長＋余裕で設定）に書き換えて返す。**S3署名URLの7日上限を「リンクの寿命」と混同しない**：リンクの寿命はtoken（revokeまで有効）、署名は再生のたびに短命発行。署名クエリ付きURLはCDNキャッシュが効かない点は許容（R2 egress無料） |

### 認証

| メソッド/パス | 内容 |
|---|---|
| `GET /api/auth/line/start` | LINE Login **v2.1 authorization code flow** の開始。state＋PKCE verifier をRedis（10分）に保存し、LINE認可URLへ302（LIFFは使わない。PWAの通常ブラウザ文脈で動かす） |
| `GET /api/auth/line/callback` | LINE側に登録するコールバック。code＋state検証 → トークン交換 → IDトークンをチャネルIDで audience 検証 → auth_providers に upsert → Redisセッション発行 → フロントへ302。Cookie: HttpOnly + Secure + SameSite=Lax、30日 |
| `POST /api/auth/logout` | セッション破棄 |

- 登録フローで**メールアドレスを必ず取得**：LINEのメール取得許諾（申請済みチャネル）を第一、
  未許諾時は初回ログイン後に手入力画面（`PATCH /api/me` `{email}`）で取得。
  `users.email` はNULL可（devユーザー・取得前状態）だが、M5完了条件では
  LINE登録フローでの取得率100%を確認する。
- `provider: email_magic` は **Phase 1**（スキーマだけ先行）。メール送信基盤は Resend を採用
  （channels/email と共用。M5でAPIキーを設定）。
- **友だち判定**：Messaging API の follow/unfollow webhook を受信して
  auth_providers.meta に保持（profile APIのプローブはしない）。
- **PWA standalone（ホーム追加）モードでのOAuthリダイレクト＋Cookie持続の動作確認をM5の完了条件に含める**（iOSの既知の落とし穴）。
- 通知は `channels/` のアダプタ経由でのみ送る。Phase 0 実装は line / email / noop の3つ。
  LINE Login（認証）と Messaging API（push）は**別チャネル**であり、友だち追加していない
  ユーザーにpushは送れない → ログイン後に友だち追加を導線化し、未友だちはemailへフォールバック、
  それも無ければアプリ内表示のみ。

## ジョブフロー

```
POST /matches
  → [cpu] precheck（原本に対して ffprobe ＋ 先頭60秒・2fps のコート検出・画角・固定・輝度判定。
      [03](03-recording-guidelines.md)。moovが末尾の場合は末尾Range取得。
      **GPU起動前に**入力不正（コーデック非対応・音声のみ等）は failed(input_invalid) で弾き、
      撮影NG系の警告はここで即ユーザーに返す）
      ├─ コート検出OK/警告 → 続行（警告 — 画角・手ブレ・輝度・低解像度・縦動画 — は
      │   全て記録の上で自動続行。ユーザー確認は挟まない）
      └─ コート検出NG → **縮退モード**フラグを立てて続行
          （segmentation.v1.yaml の degraded パラメータセット：中央ROIの人物モーションのみ）
  → [gpu] ingest → analyze（同一コンテナで連続実行。ディスパッチャが起動）
      ingest: 回転正規化・HEVC/HDR→H.264/SDR（GOP 2s, 8Mbps）・CFRプロキシ生成（[02](02-architecture.md)）
      analyze: stage1-4 → event_streams v1 + segments revision0（縮退時は stage2/4 のみ）
  → [cpu] edit（有効区間をキーフレームに外側スナップして -c copy 連結。
      スナップ後の区間間隔が min_gap_s 未満なら結合（クリップ重複防止、segmentation.v1.yaml）
      → HLS生成（単一レンディション・6秒セグメント・オーバーレイなし）→ thumbnail生成）
  → status=done、channels経由で完了通知（M2〜M4は noop チャネル固定 — 通知は実質M5から）
POST /recut → [cpu] edit のみ再実行（video_assets.generation+1）
```

- `preflight_report` のスキーマ：`{checks: {court: {result: ok|warn|fail, value, message},
  coverage: {...}, stability: {...}, brightness: {...}, resolution: {...}},
  degraded: bool, sampled_range_s: [0, 60]}`。matches.preflight_report に保存
  （[03](03-recording-guidelines.md) と同一定義。イベントストリームには入れない）。

### 冪等性・リトライ（実装要件）

- 全ジョブは match_id + 入力アセット世代で決まり、再実行しても行を重複させない
  （event_streams はversion+1、segments/assetsはgeneration方式、jobs はattempt+1）。
- **失敗の分類**：恒久失敗（入力不正・コーデック非対応）は即 status=failed＋failure_reason。
  一時失敗（OOM・ネットワーク・スポット中断）のみ指数バックオフで最大3回。
- **ポイズンピル対策（配送回数ベースの打ち切り）**：ワーカーごと死ぬ失敗（GPU OOM・
  ドライバクラッシュ・特定動画でのデコーダ落ち）はブローカー再配送であり **Celeryの
  retryカウンタを増やさない**。タスク実行の冒頭で `analysis_jobs.attempt` をDBで
  インクリメントし、しきい値（5）超過なら即 failed(retry_exhausted) にする。
  これが無いと同じ動画がGPU課金を永久に焼き続ける。
- ワーカー喪失の受け直し：Celeryは `acks_late=True` + `task_reject_on_worker_lost=True`、
  Redisブローカーの `visibility_timeout` はジョブ最長時間（60分）×2 に明示設定。
- 失敗時のrequeue（`make requeue MATCH=..`）は **status=failed のmatchのみ**受け付ける。
  done後の再解析（イベントストリームv2生成とsegments再初期化の規則）はPhase 1で定義し、
  Phase 0では実装しない。
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
// stage1 出力
{"court_detected": true, "homography": [[...3x3...]], "court_polygon_px": [[x,y]×4],
 "court_type": "unknown", "confidence": 0.91, "spec_version": "court-spec.v1"}
// stage2 出力（コート内判定に stage1 の court_polygon_px を使う。縮退時は中央ROI）
{"hz": 5, "per_frame": [{"t": 0.2, "n_persons": 4, "person_motion": 0.31}],
 "confidence": 0.9}
// stage3 出力（各時点は隣接3フレームバーストから算出。segmentation.v1.yaml の sampling 参照）
{"hz": 5, "per_frame": [{"t": 0.2, "ball_motion": 0.44}], "confidence": 0.7}
// stage4 入力は stage2/3 の per_frame。合成式と重みは segmentation.v1.yaml（activity節）:
//   combined = w_person * person_motion + w_ball * ball_motion
// stage4 出力（= event_streams.points の素）
{"segments": [{"start_s": 613.2, "end_s": 641.8, "confidence": 0.84}],
 "params_version": "segmentation.v1"}
```

- 各ステージは `stage_input.json → stage_output.json` の独立CLIとしても実行可能にする
  （ゴールデンセット回帰・デバッグ用。不変原則3）。
- 区間判定は**プレー区間を削らない方向に倒す**（適合率優先。[01](01-mvp-scope.md)）。

## ゴールデンセット（調達と判定を仕様化）

- **調達はM1期間中のタスク**：ユーザー自身（開発者）が3条件（オムニ/ハード/画角悪）で
  実際に撮影する。M3開始時に3本無ければM3は開始できない（クリティカルパス）。
  Phase 0完了までに10本へ拡充（知人サークルの協力。同意書テンプレートを用意）。
- 正解ラベル：`golden/labels/{id}.json` = `{"segments": [{"start_s", "end_s"}], "notes"}`。
  ゴールデンセットには**縮退モードの再実行ケース**（コート検出不能扱いで同一動画を評価）も含める。
- 合否判定（`make golden` で実行）。判定アルゴリズムは以下の1つに固定：

```python
def is_match(pred, gt):   # 予測区間と正解区間の一致判定
    if abs(pred.start_s - gt.start_s) <= 1.0 and abs(pred.end_s - gt.end_s) <= 1.0:
        return True       # 境界が両端とも±1.0s以内なら一致
    return iou(pred, gt) >= 0.8   # そうでなければIoUで判定
# 貪欲マッチング（IoU降順）で1:1対応させ、
# precision = matched / len(pred), recall = matched / len(gt)
# ゲート: precision >= 0.90 かつ recall >= 0.80（どちらか下回ればfail。08も同一基準）
```

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
| M2 | precheck（**メタデータ検査のみ**。コート検出はM3）+ ingest（正規化）+ **GPUジョブディスパッチャ** + editワーカー + HLS + 視聴ページ。analyzeは**スタブ**（segmentsに固定3区間をsource=autoでINSERT） | 実スマホ動画（HEVC）をアップロード→（サーバーレスGPU実機で）正規化→（ダミー区間で）編集済みHLSが全ブラウザで再生できる。**E2Eの配管が先、CVは差し替え**。通知はM4までnoopチャネル固定 |
| M3 | precheck完全版（コート検出・縮退判定）+ stage1-4（ゴールデンセット3本で `make golden` パス、縮退ケース含む） | 実動画で区間が自動検出されM2の配管に流れる。スタブと同じくsegmentsに書くだけなので差し替えは1点 |
| M4 | 区間修正UI + PATCH（楽観ロック）+ recut（世代管理） | 誤検出をユーザーが直して再編集できる。2タブ同時編集で409が返る |
| M5 | LINEログイン（start/callback + メール取得）+ channels（line/email/noop、followウェブフック）+ 完了通知 + 共有リンク + **保持削除ジョブ（日次、全員Free扱い）** | 通しのユーザー体験が成立。**PWA standaloneでのログイン動作確認・メール取得率100%を含む**（Phase 0 完了） |

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
