# 12. フォーム解析のショット別拡張（Phase 3拡張）

## 決定（2026-07-11 ユーザー決定）

Phase 3のフォーム解析を**サーブ専用から主要ショット全種へ拡張**する。
対象は5種：**serve / forehand / backhand / smash / volley**。

サーブ実装（stage6_pose.py + serve-mechanics.v1.yaml）で確立したパターン
（MediaPipe world landmarks → フェーズ分割 → 正規化指標 → YAML参照レンジ比較）を
一般化し、ショット種別ごとのフェーズモデル・指標セットをYAMLで宣言できる構造にする。

## スコープの境界（先に決めておく「やらないこと」）

| やらないこと | 理由 |
|---|---|
| **試合動画からのフォーム解析** | ベースライン後方の遠距離画角では姿勢推定が破綻する（ブリーフ5-3、01 §理由3）。フォーム解析は**練習撮り専用モード**（近距離・単独被写体）に限定する |
| **ショット種別のCV自動判定** | ユーザーがセッション作成時に申告する（self_side方式のワンタップ）。CVで推定して誤るより申告が確実（不変原則1） |
| **特定プロとの比較** | 06で決定済み。文献レンジ＋契約コーチ撮り下ろしの2本立てを全ショットに適用 |
| **スイング速度の絶対値評価** | スマホ単眼30fpsでは高速スイング時の手首がモーションブラーで流れる。速度系はスイング分割の内部信号にのみ使い、ユーザー向け指標は**コンタクト前後の関節角度・相対位置・タイミング比**を主体にする |
| **advice-rulesへの組み込み** | 週次ダイジェスト等への統合は将来論点。v1はフォームセッション画面内で完結（yagni-guard） |

## ショット別フェーズモデル

形態が異なるためフェーズモデルは3系統。**smashはserveの変形**（トスが無く、
非利き腕のポインティングがトス腕の役割を代替）なので検出器を共有する。

| ショット | フェーズ | キーイベント検出（ヒューリスティック） |
|---|---|---|
| serve / smash | preparation → toss(※) → trophy → acceleration → impact → follow_through | 非利き手首の最高点（トス頂点/ポインティング頂点）、軸足膝の最大屈曲（トロフィー）、利き手首の最高点（インパクト）。現行stage6の検出器をそのまま流用 |
| forehand / backhand | ready → backswing → forward_swing → contact → follow_through | backswing_end＝利き手首が骨盤基準で最も後方に達した時点、contact＝利き手首スピードのピーク、follow_end＝スピードが閾値を割った時点 |
| volley | ready → punch → contact → recovery | contact＝利き手首が体の前方（骨盤前面基準）で最も遠くに達した時点。**ボレーはスイングしない**のが要点なので、コンタクト前後の肘角度変化量そのものを主要指標にする |

※ smashではフェーズ名を `point`（ポインティング）と読み替える。YAMLの `phase_labels` で表示名を差し替え。

### ハンドネス・スタイルの扱い

- **利き腕**：ユーザープロフィールに保持（初回に1タップで申告）。未設定時は現行の
  自動推定ヒューリスティック（両手首の可動レンジ比較）にフォールバックし、
  推定結果を信頼度付きで表示・修正可能にする（不変原則1）。
- **両手バックハンド**：backhandセッションのみの属性。コンタクト時の両手首間距離で
  自動判定できる（両手打ちなら手首間距離≒0）が、v1はセッション作成時に
  片手/両手/自動 の3択で申告させ、「自動」時のみ検出を使う。
  指標定義はYAMLの `only_style: one_handed | two_handed` フィルタで出し分ける
  （例：肩腰捻転差の参照レンジは両手打ちで狭くなる）。
- **前脚/後脚**：serve/smashは「非利き腕側＝前脚」で確定的に解決できる。
  グラウンドストロークはオープン/スクエアスタンスで変わるため、v1は
  利き腕側/非利き腕側の命名のみを使い、スタンス依存はドキュメント上の既知の限界とする。

## 1動画=複数スイング前提（サーブv1の暗黙制約の解消）

現行サーブ実装は動画全体を1本のサーブとして解析している。練習動画は
球出し・サーブ練習とも**1動画に数十スイング**が normal case なので、
スイング分割レイヤを新設し全ショット（サーブ含む）に適用する。

```
動画 → precheck（pose probe） → ランドマーク抽出（30Hz・12関節・world座標）
     → [S3にランドマーク系列を保存]  ←不変原則3の中間出力
     → スイング分割（利き手首スピードのピーク検出 + min_interval + 前後窓切り出し）
     → 各スイング: フェーズ検出（ショット別detector） → 指標算出（プリミティブ×YAML）
     → セッション集約（指標ごとに 中央値・IQR・有効本数） → レンジ比較 → 上位N件フィードバック
```

- **ランドマーク系列のS3保存**が新規。JSONB直入れはサイズが重い
  （60秒×30Hz×12関節で gzip後 ~150KB、生JSONで ~700KB）ため、
  `form-sessions/{id}/landmarks.v1.json.gz` としてS3に置き、DBは参照キーのみ持つ。
  これにより **shot-mechanics.yamlの指標変更時に骨格再抽出なしで指標だけ再計算**できる
  （taxonomyのミス分類再計算と同型。不変原則3）。
- **集約は中央値+IQR**。平均は失敗スイング1本に引きずられる。IQRは
  「ばらつき」そのものがコーチング情報（打点が毎回バラつく等）なので指標化する。
  `consistency_cv_max` を持つ指標は IQR/中央値 がそれを超えたとき
  「ばらつきが大きい」フィードバック候補になる。
- **有効本数ゲート**：visibility基準を満たすスイングが `min_valid_swings`（既定3）未満なら
  セッションを `insufficient_data` とし、指標を出さずに再撮影ガイドを提示する
  （06 §比較アルゴリズム5と同じフォールバック方針）。

## 指標エンジン：計算プリミティブ × YAML宣言

現行stage6は指標IDごとの `elif` 分岐で計算式がコードに固定されており、
不変原則2（カテゴリ追加はYAML編集のみで完結）を満たしていない。拡張にあわせて
**少数の計算プリミティブ（コード）と指標定義（YAML）に分離**する。

プリミティブ（v1で6個。これ以上は必要になるまで足さない）：

| primitive | 意味 | args |
|---|---|---|
| `joint_angle` | 3関節のなす角（度） | `points: [a, b, c]`（bが頂点） |
| `relative_height` | 基準点からの高さ / 体幹長 | `point`, `ref`, 体幹長=利き肩-利き腰 |
| `forward_of_body` | 骨盤前面からの前方距離 / 体幹長 | `point` |
| `line_separation` | 2つの体節ライン（肩・腰）の回旋差（度） | `lines: [shoulder_line, hip_line]` |
| `event_interval` | 2キーイベント間の時間（ms） | `from_event`, `to_event` |
| `angle_delta` | 2キーイベント間での関節角度変化量（度） | `points`, `from_event`, `to_event` |

- 関節参照は `dominant_wrist` / `nondominant_knee` のようなロール名で書き、
  ハンドネス解決はエンジン側で行う。
- 実在しないロール名・イベント名を参照する指標はロード時のスキーマ検証で拒否する
  （taxonomyの「存在しない参照はスキーマ検証で拒否」と同じ規約）。

## 設定ファイル：shot-mechanics.v1.yaml（serve-mechanics.v1.yaml を統合・置換）

実ファイル：[config/shot-mechanics.v1.yaml](../../config/shot-mechanics.v1.yaml)。スキーマ骨子：

```yaml
version: 1
citation_status: placeholder_pending_literature_review
defaults:
  min_landmark_visibility: 0.6
  max_feedback_metrics: 3
swing_detection:
  min_peak_speed_mps: 3.0      # world座標基準。placeholder
  min_interval_s: 1.5
  window_pre_s: 1.5
  window_post_s: 1.0
  min_valid_swings: 3
shots:
  forehand:
    detector: groundstroke     # コード側detector名
    phases: [ready, backswing, forward_swing, contact, follow_through]
    metrics:
      - id: contact_forward_of_hip
        at: contact            # detectorが提供するキーイベント名
        primitive: forward_of_body
        args: {point: dominant_wrist}
        unit: relative_torso
        elite_range: [0.3, 0.7]
        tolerance: 0.1
        consistency_cv_max: 0.25   # ばらつき警告のしきい値（任意キー）
        advice_key: contact_point
        source: placeholder
      # ...
  backhand:
    detector: groundstroke
    metrics:
      - id: shoulder_hip_separation_at_backswing
        only_style: two_handed     # スタイル別出し分け（任意キー）
        # ...
```

- **serve-mechanics.v1.yaml は本ファイルに統合して廃止**する（serveセクションとして移設）。
  未リリースの設定のため互換維持は不要。stage6が新ローダーへ切り替わったコミットで
  旧ファイルを削除する（それまで旧ファイル冒頭に後継ファイルへの参照コメントを置く）。
- 全ショットの `elite_range` は**文献レビュー未完了のplaceholder**。serveと同じ
  `citation_status` ゲートで「参考値（検証中）」表記をUI/文言生成に強制する。
  検証の当てはITF Coaching & Sport Science Review系の文献だが、
  **volley/smashは文献自体が薄い**ことが既知のリスク（後述のロールアウト順に反映）。

## ショット別の初期指標セット（すべてplaceholder、実ファイルが正）

| ショット | 指標（抜粋） |
|---|---|
| serve | 既存6指標を移設（膝屈曲@トロフィー、肘高@トロフィー、肩腰捻転差、肘伸展@インパクト、打点高、トス頂点→インパクトms） |
| forehand | 肩腰捻転差@backswing_end、コンタクトの前方位置、打点高、backswing→contact ms、肘角度@contact（レンジ広め・参考扱い） |
| backhand | forehand相当＋スタイル別出し分け（両手打ちは捻転差レンジを狭く、片手打ちは肘伸展を追加） |
| smash | serve系の移用（ポインティング腕頂点、肘伸展@インパクト、打点高、捻転差）。トス系タイミング指標は除外 |
| volley | **肘角度変化量（punch判定：小さいほど良い）**、コンタクトの前方位置、膝屈曲@contact |

## 撮影ガイドライン（03の追補）

| ショット | 推奨アングル | 備考 |
|---|---|---|
| serve / smash | 斜め後方 3〜6m（既存の serve モードと同じ） | |
| forehand / backhand | 打球方向に対して**真横〜斜め後方** 3〜6m | 回旋系指標（捻転差）は斜め後方が有利、前方距離系は真横が有利。v1は両対応の中間「斜め後方45°」を推奨に |
| volley | 斜め後方 2〜4m（ネット際なので近め） | |

共通：全身が常時フレーム内・被写体は原則1人（複数人が映る場合は最大サイズの人物を採用し、
その旨を信頼度と一緒に表示）・縦横どちらも可。

**preflight pose probe を新設**：本解析（GPU/長時間）の前に、先頭数秒を低Hzで
姿勢推定し、検出率が低ければ「全身が映っていません/被写体が小さすぎます」を
アップロード直後に警告する（Phase 0のprecheckと同じ「安価に先に弾く」思想、10）。

## DB / API（実装仕様の要点）

- `serve_sessions` → **`form_sessions`** にリネームし `shot_type` 列
  （enum: serve/forehand/backhand/smash/volley）を追加。`serve_analyses` → `form_analyses`。
  既存データは shot_type='serve' で移行（未リリースなのでリネームマイグレーションで問題ない）。
  ※ このenumは**練習セッションの申告種別**であり、taxonomy.v1.yaml の shot_type 軸
  （試合中のCV分類。volley_smashが統合値）とは別物。混同しないこと。
- 新カラム：`backhand_style`（one_handed/two_handed/auto、backhandのみ意味を持つ）、
  `landmarks_r2_key`（S3中間出力への参照）。
- API：`/api/serve-sessions` → `/api/form-sessions`（作成時に `shot_type` 必須）。
  旧ルートは置換（クライアント未リリース）。
- 解析結果payloadに追加：`swings`（スイングごとの指標値とvisibility）、
  `aggregate`（指標ごとの median/IQR/valid_count）、`insufficient_data` フラグ。
- ジョブ：`run_form_analyze` に改名。ランドマーク抽出とその後段（分割→指標→集約）を
  関数境界で分離し、S3のランドマーク系列からの**指標のみ再計算**を可能に保つ
  （再計算ジョブ・APIの実装自体は必要になるまで作らない。境界だけ確保する）。

## UI（11の追補）

- `/serve` 一覧 → `/form` に改名し、作成時にショット種別チップ（5択）を選択。
- 詳細画面：集約カード（注目ポイント上位N件 → 全指標。既存serveと同じ構成）＋
  **スイング一覧ストリップ**（有効/無効と外れ値スイングが見える。タップで該当スイングの値）。
- ばらつき警告は専用の表現（レンジ逸脱の赤系とは区別し、sand系で「毎回変わっています」トーン）。
- 「参考値（検証中）」の断り書きと骨格検出率の表示は既存serveの規約を踏襲。

## ロールアウト順（Phase 3内の段階導入）

| 段階 | 対象 | 根拠 |
|---|---|---|
| 3a（済） | serve | 実装済み。3bで複数スイング対応に載せ替え |
| 3b | forehand / backhand | ユーザー需要が最大・文献も比較的厚い。スイング分割・プリミティブエンジン・form_sessionsリネームはここで導入 |
| 3c | smash | serve検出器の流用で実装コスト最小 |
| 3d | volley | 文献が最も薄く、参照レンジの正当化が最難。最後に回し、レンジ検証が済むまで「測定値の提示のみ（レンジ比較なし）」での先行公開も許容 |

各段階の公開ゲート＝該当ショットの `elite_range` の文献裏取り完了
（それまでは citation_status ゲートの「参考値（検証中）」表記で限定公開）。

## リスク

| リスク | 対応 |
|---|---|
| volley/smashの文献レンジが確保できない | レンジ比較を出さず測定値＋ばらつきのみ表示するモードを許容（3d） |
| グラウンドストロークのスタンス依存（オープン/スクエア） | v1は利き腕側/非利き腕側の命名に留め、既知の限界として明記 |
| 高速スイングのモーションブラー | 速度系をユーザー向け指標にしない。コンタクト検出が不安定なスイングはvisibilityと同様に無効扱い |
| 複数人の映り込み（球出しコーチ等） | num_poses=1で最大人物を採用し、採用対象の不確かさを表示。改善は将来（撮影ガイドで1人を推奨） |
| 両手バック判定の誤り | 申告優先・自動は信頼度付き・修正可能（不変原則1） |
