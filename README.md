# Tennis Analyzer 🎾

スマートフォン1台で撮影したテニスの試合・練習動画をアップロードするだけで、
**スタッツ・ミス分析・ハイライト動画・継続的なアドバイス** を自動生成するアプリの設計リポジトリ。

## 解決する課題

1. 試合・練習動画の編集（ポイント間のカット、ハイライト抽出）に手間がかかる
2. その結果「振り返る → 改善する → 練習する」のサイクルが遅くなる
3. 動画共有にも時間がかかる

## 差別化ポイント（競合調査より）

| 領域 | 競合 | 本アプリの差別化 |
|---|---|---|
| 試合スタッツ・ハイライト | SwingVision | 日本語ネイティブ、粒度調整可能なミス分類、オムニコート対応前提 |
| フォーム骨格解析 | ForceSense 等 | 試合分析とフォーム解析の統合 |
| ミス原因分析＋継続アドバイス | 直接競合なし | **最大の付加価値ポイント** |

## ドキュメント構成

| ドキュメント | 内容 |
|---|---|
| [docs/design/00-overview.md](docs/design/00-overview.md) | 設計サマリと意思決定一覧 |
| [docs/design/01-mvp-scope.md](docs/design/01-mvp-scope.md) | MVPスコープとフェーズ計画 |
| [docs/design/02-architecture.md](docs/design/02-architecture.md) | システムアーキテクチャ・解析パイプライン |
| [docs/design/03-recording-guidelines.md](docs/design/03-recording-guidelines.md) | 撮影要件（カメラ位置・角度・プリフライトチェック） |
| [docs/design/04-miss-taxonomy.md](docs/design/04-miss-taxonomy.md) | 粒度可変ミス分類の設計（ルールエンジン） |
| [docs/design/05-tech-stack.md](docs/design/05-tech-stack.md) | 技術選定（CV / 動画処理 / LLM / インフラ） |
| [docs/design/06-pro-reference-data.md](docs/design/06-pro-reference-data.md) | プロ比較用参照データの調達戦略 |
| [docs/design/07-advice-delivery.md](docs/design/07-advice-delivery.md) | 継続アドバイス配信の仕組み |
| [config/taxonomy.v1.yaml](config/taxonomy.v1.yaml) | ミス分類定義（v1初期粒度） |
| [config/advice-rules.v1.yaml](config/advice-rules.v1.yaml) | アドバイス発火ルール定義 |

## ステータス

設計フェーズ。実装は [01-mvp-scope.md](docs/design/01-mvp-scope.md) のフェーズ計画に従って着手する。
