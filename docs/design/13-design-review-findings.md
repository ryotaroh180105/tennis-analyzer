# 13. 設計レビュー指摘と実装パンチリスト（2026-07-11）

実装を本格化する前の設計監査（fableによる最終チェック）の結果。5領域（アーキ/実装計画・
分類/アドバイスエンジン・フォーム解析・UI/撮影・運用/GTM/権利）を設計ドキュメント／config／
実装コードと突き合わせて抽出した。**致命的な実装ブロッカーは無し**。権利制約（06）は
`advice_llm.py` で能動的に守られ、Phase0/1布石（チャネル抽象・i18nバックエンド・court-spec）
と不変原則4（LLMに集計JSONのみ）も遵守を確認済み。

以下は「設計文書では約束したが実体で満たされていない」ギャップの一覧。`[fable済]` は
本レビューで設計判断・ドキュメント同期を完了、`[実装]` はSonnetによるコード対応が必要。

---

## A. 系統的な設計ギャップ（実装前に潰す）

### A-1. ロード時スキーマ検証が全YAMLサブシステムで欠落 `[実装]`

- 事象：`taxonomy_engine.py:24-28` / `advice_engine.py:21-25` / `config_loader.py:30-34`
  はいずれも `yaml.safe_load` のみで検証ゼロ。設計（04・07・12:96-97、各YAMLヘッダ）が
  約束する「実在しない参照はロード時に拒否」が未実装で、`taxonomy_engine.py:73-87` は
  未実在フィールドを黙って `_UNRESOLVED`→False に倒す（**拒否の真逆**）。
- 影響：不変原則2（YAML編集だけでカテゴリ追加が完結）の前提が崩壊。タイポしたトリガーが
  「永久に発火しないルール」として黙って通り、回帰でも検出できない。
- 対応方針（確定）：**共有のpydanticロード時バリデータ**を必須コンポーネントに格上げする。
  検証項目：(1)実在しないフィールド/ロール/イベント/primitive参照の拒否、(2)labelsの
  catch-all `match:{}` 必須、(3)ルールの `default` 必須、(4)ロケールキー型ラベル、
  (5)shot-mechanicsの `elite_range` と `expected_sign` の排他。不正はロード時に例外。

### A-2. 定性評価 `expected_sign` が利き手非対応（左利き誤判定）`[fable済: 設計確定 / 実装: 符号正規化]`

- 事象：`primitives.py:92-100` の `line_separation_signed` は `dominant_side` を受け取るが
  未使用で、符号を解剖学的固定（right−left）で返す。YAMLの `expected_sign`（片手=positive
  `shot-mechanics.v1.yaml:289`、両手=negative `:304`）は右利き前提。左利き片手バックは
  回旋が鏡像で符号反転 →**正しいフォームを `out_of_range`**（原則1違反、左利き全員該当）。
- 対応方針（確定・12-form-analysis.md §評価モードに記載）：`line_separation_signed` を
  **利き手基準で符号正規化**する（例：`dominant_side=="left"` のとき符号反転）。YAMLの
  `expected_sign` は利き手非依存の固定値のまま。定量の `line_separation` は `abs()` で
  無事なので変更不要。テスト：左利き合成データで正しいフォームが `in_range` になること。

### A-3. placeholderレンジがコーチング生成（3d「測定値のみ」の実現機構が未設計）`[fable済: 設計確定 / 実装]`

- 事象：`metrics_engine.py:66-72` の `evaluate_status` は全 `elite_range` を無条件で判定。
  `source: placeholder` のsmash4指標（`:328,338,348,358`）・volley未検証2指標も
  out_of_range→注目ポイントに載る。だが設計（12 §ロールアウト3d、12a）は「smash/volleyは
  レンジ比較を出さず測定値のみ表示」。**`source` はコード全体で一度も読まれていない**。
- 対応方針（確定・12-form-analysis.md §評価モードに記載）：`elite_range` も `expected_sign`
  も持たない指標を **`status: measured`（比較なし・注目ポイント対象外）** として扱う。
  実装ではsmash/volleyのplaceholder数値レンジをconfigから外す（推測値を書かない）。
  UIは測定値のみ表示（既存の縮退表示と同系統）。

---

## B. 不変原則1（誠実さ＝低信頼はunknown）が複数箇所で死んでいる `[実装]`

- **B-1 `winner_min_confidence`(0.75) 未実装** `taxonomy_engine.py:179-184` — outcome汎用
  `min_confidence`(0.6)しか見ず、doc04が定めたウィナー専用しきい値（`taxonomy.v1.yaml:63`）が
  デッドパラメータ。confidence 0.65〜0.74 のショットが winner 確定。**原則1の中核**。
- **B-2 低信頼区間がリボンで不可視** — `Ribbon.tsx` は `lowConfidence` 分岐を持つが
  `api.ts:28-31` の `SegmentEffective` が `confidence` を運ばず常にundefined。誠実さ表現が
  シグネチャ要素でデッドコード。API→型→受け渡しに confidence を通す。
- **B-3 完了ビューで縮退バナーが消える** — `matches/[id]/page.tsx:157-176` で `!isDone`
  条件内にのみ存在。修正判断の場面で文脈が消える（11章は完了ビューに置くと明記）。
- **B-4 定性 out_of_range が severity=0 で注目ポイントから脱落** — `orchestrator.py:57-61`。
  実在するフォーム欠陥でも数値指標に押し出される。定性 out_of_range に非ゼロの重みを与える。

---

## C. 不変原則3（ステージ独立・中間出力保存）が未達 `[実装 / 方針は既存docで確定済み]`

- **C-1 stage1-3の中間出力を保存せず、下流のみ再実行が不可能** — `pipeline.py:13-78` が
  メモリ内連続実行、`tasks.py:238-252` で `event_streams`/`segments` だけ永続化。taxonomy変更で
  CVをやり直さず再計算する経路が無く、リトライは毎回stage1から（`tasks.py:209`）。設計02:53/
  10:224 が要求する stage単位再開が未実装。
- **C-2 ステージ独立CLI（`stage_input.json→stage_output.json`）未実装**（設計10:255）。
- **C-3 GPUディスパッチャ未実装・廃止予定のCelery gpuキューで代替** — `celery_app.py:52-54`,
  `docker-compose.yml:134-156`。00決定7「サーバーレスGPU・常駐なし」と矛盾。本番切替時に手戻り。

## D. 「初日から」取るべき原価データが取れていない（後から遡れない）`[実装済み]`

- **D-1 ステージ別GPU秒を記録していない** — 解消。`cvpipeline/pipeline.py`の`run_analyze`が
  各ステージ（court/players/ball/segments/shots）をtime.monotonic()で計測し
  `stage_seconds: {stage1_s..stage5_s}`を返す。`tasks.py`のrun_analyzeジョブがこれを
  breakdownにそのまま展開する。
- **D-2 `gpu_seconds` にI/O待ち(DL/UL)を混入** — 解消。`run_ingest`/`run_analyze`とも
  download_s/upload_sを個別に計測し、`gpu_seconds`はGPU/CPU計算コスト（encode_sまたは
  stage_secondsの合計）のみを表すよう変更。契約キー（10:87-88の
  `{download_s, encode_s, stage1_s..stage4_s, upload_s}`）を満たす（stage5_sは追加の拡張キー）。

---

## E. ドキュメント同期債務 `[fable済]`

- **E-1** CLAUDE.md：プリミティブ数「6個」→「7個・一覧は12が正」、`serve-mechanics.v1.yaml`
  「廃止予定」→「削除済み」、`expected_sign`/ロード時検証の追記。**完了**。
- **E-2** 00-overview 論点12：定性評価モード・測定値のみ表示を反映。**完了**。
- **E-3** 06：廃止済み `serve-mechanics.v1.yaml` 参照を `shot-mechanics.v1.yaml` に修正
  （`:25`, `:73`）。**完了**。
- **E-4** 12-form-analysis：プリミティブ表に `line_separation_signed` 追加＋評価モード規約
  （符号の利き手正規化・測定値のみモード）を新設。**完了**。

## E'. その他の未実装（設計文書にはあるが実体が無い。優先度中〜低）`[実装]`

- precheckしきい値がコード内定数（`precheck.py:9-11`、原則2グレー）→ config外出し。
- 03章の5チェックのうち画角カバレッジ・カメラ固定・明るさの3つ未実装。degraded以外の
  warn（resolution/framerate/orientation）がUIに出ない（`matches/[id]/page.tsx:157`）。
- ダークテーマ到達不能（`data-theme` を設定する箇所がフロントに無い、`globals.css:2-3`）。
- i18nキー化未実装（文言ハードコード、`api.ts:226-300` 等）。バックエンドの `User.locale` と
  ロケールキー型YAMLの布石はあるが、フロントに辞書レイヤが無い。
- 共有視聴ページにリボン（読み取り専用）が無い（11章:123）。スイング一覧ストリップ未実装
  （12章:193）。データ保持バッチ（原本30日削除等、08:127-134 / M5）未実装。
- frontend `FORM_PHASE_LABEL_JA` に `toss_apex` が無く生キー表示（`api.ts:257-269`）。
- ゴールデンセット回帰の自動ゲートがCI未配線（機構 `golden_runner.py` は実装済み）。

---

## 確認済み（問題なし）

- 不変原則4：`advice_llm.py:72-78,101-107` はClaude APIへ集計済みスタッツJSONのみ。
- 権利制約（06）：`advice_llm.py:27,46` がプロンプトで選手名・プロ比較・映像言及を能動禁止。
- Phase0/1布石：チャネル抽象（`backend/app/channels/`）・i18n（`User.locale`）・court-spec外出し。
- フォーム解析E2Eの型整合：`elite_range=None` は schema/`formatRange`/`aggregate_metric` の
  空値分岐で正しく処理されクラッシュしない（A-2/A-3は判定内容の誤りであって型崩れではない）。
- serve-mechanics.v1.yaml のconfigからの物理削除・shot-mechanicsへの統合は完了済み。
- 課金/プラン未実装はPhase1スコープ（09:135）で仕様通り、矛盾ではない。
