# 04. 粒度可変ミス分類の設計（ルールエンジン）

## 要求（ブリーフより）

- ミスの数と種類を自分・相手それぞれ記録する
- **粒度は可変・調整可能**。分類軸を後から追加・変更できること
- 「何がミスで、何が甘い球で、何が良いショットか」の判断基準自体をパラメータ化すること

## 設計：分類は「軸の直積」＋「判定式」で宣言する

分類カテゴリを列挙するのではなく、**軸（dimension）** と **判定ルール（rule）** を
YAMLで宣言し、ルールエンジンがイベントストリームに適用する構造にする。
カテゴリの追加＝YAMLの行追加であり、コード変更は不要。

### 概念モデル

```
EventStream (ショット列・終端イベント)
      │
      ▼
┌─ TaxonomyConfig (YAML) ──────────────────────────┐
│ dimensions:  分類軸の定義（ショット種別、結果、状況…） │
│ rules:       各軸の値を決める判定式                  │
│ labels:      軸の組合せに与える表示名・重要度          │
│ thresholds:  「甘い球」「良いショット」等の判断基準      │
└──────────────────────────────────────────────────┘
      │
      ▼
ClassifiedPoint (軸ごとの値 + ラベル + 重要度)
      │
      ├─▶ スタッツ集計（軸の任意の組合せでピボット可能）
      ├─▶ ハイライト選定（importance で抽出）
      └─▶ Claude API への構造化入力
```

### v1 の初期粒度

| 軸 | 値 | 判定ソース |
|---|---|---|
| `shot_type` | serve / forehand / backhand / volley_smash | CVステージ6 |
| `outcome` | net / out / winner / in_play / unknown | CVステージ7＋ユーザー修正 |
| `pressure` | forced / unforced | 直前の相手ショットの深さ・テンポ（判定式。**球速はスマホ単眼30fpsで信頼できないためv1では使わない**） |

3軸で `4 × 5 × 2 = 40` セルだが、スタッツ表示は任意の軸で畳み込める
（例：「バックハンドの非強制ミス」= `shot_type=backhand AND outcome IN (net,out) AND pressure=unforced`）。

### v2 以降の拡張例（YAML追加のみで実現）

- `direction` 軸（クロス/ストレート/逆クロス）→ 配球パターン分析
- `depth` 軸（浅い/深い）→ 「甘い球」判定
- `game_situation` 軸（ブレークポイント/デュース…）→ プレッシャー状況分析
- `serve_number` 軸（1st/2nd）

## taxonomy.yaml の構造

実ファイルは [config/taxonomy.v1.yaml](../../config/taxonomy.v1.yaml)。構造の要点：

```yaml
version: 1
dimensions:
  - id: shot_type
    source: cv.shot.type          # イベントストリームのフィールドから直接
    values: [serve, forehand, backhand, volley_smash]

  - id: pressure
    source: rule                   # 判定式で導出
    values: [forced, unforced]
    rules:
      - value: forced
        when: "prev_opponent_shot.landing_depth > thresholds.forcing_depth
               or prev_opponent_shot.interval_s < thresholds.forcing_tempo_s"
      - value: unforced
        when: "default"

thresholds:                        # ← 「判断基準のパラメータ化」
  forcing_depth: 0.8               # コート奥行きの正規化値
  forcing_tempo_s: 1.1             # 直前ショットからの間隔（秒）
  weak_ball_depth: 0.45            # これより浅い返球は「甘い球」
  rally_long: 9                    # ハイライト対象の長ラリー

labels:
  - match: {shot_type: backhand, outcome: [net, out], pressure: unforced}
    label: { ja: "バックハンドの凡ミス" }   # ロケールキー型（i18n）
    importance: high               # ハイライト・アドバイスの優先度
  - match: {outcome: winner}
    label: { ja: "ウィナー" }
    importance: high
```

**判定式が参照できるのはイベントストリームに実在するフィールドと派生フィールド
（`landing_depth`, `interval_s`。[02](02-architecture.md) で定義）のみ**。
存在しないフィールドを参照する式はスキーマ検証で拒否する。

### 判定式の実装

- `when` 式は安全なサンドボックス評価器で実行する（Python実装なら `simpleeval` 等。
  `eval` は使わない）。参照できる変数はイベントストリーム由来の読み取り専用コンテキストのみ。
  文字列リテラルは必ずクォートする（`shot.type != 'serve'`）。
- ルールは上から順に評価し、最初にマッチした値を採用。`default` は必須。
  **labels にも catch-all（`match: {}`）を必須とする**（無マッチ状態を作らない）。
- `winner_min_confidence`：outcome=winner 候補のみに適用する追加しきい値。
  `terminal.confidence` がこれ未満なら winner でなく unknown に落とす
  （誤ウィナー断定は信頼を最も損なうため、一般の `min_confidence` より厳格にする）。
- 設定ロード時にスキーマ検証（pydantic）を行い、未知フィールド・循環参照・
  **存在しないフィールドへの参照・未クォート文字列**を拒否する。

## 粒度の「ユーザー適応」

- taxonomyは**バージョン管理されたリソース**としてDBに持ち、ユーザー（またはプラン）ごとに
  参照バージョンを切り替えられる。
  - 初心者向け：3軸のみ（デフォルト）
  - 競技者向け：direction / depth 軸を有効化
  - YouTuber向け：ハイライト向け importance ルールを強化
- taxonomy変更時はイベントストリームからミス分類だけ再計算する（CV再解析は不要。
  [02-architecture.md](02-architecture.md) のステージ独立性がこれを支える）。

## unknown の扱い（再掲・重要）

CVの終端判定信頼度が低いポイントは `outcome: unknown` とし、集計上は分母から除外して
「未分類 n 件」を常に表示する。ユーザー修正で unknown が解消されるほどスタッツの精度表示が上がる、
というインセンティブ設計にする。
