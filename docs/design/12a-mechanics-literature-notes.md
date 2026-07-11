# 12a. shot-mechanics.v1.yaml 文献レビュー：進捗メモ

タスク#26の調査結果。**4指標はshot-mechanics.v1.yamlに反映済み**（下表）。
citation_statusは全体としてはまだ「検証中」のまま（理由は下記）。

## この環境からの本文PDFアクセスについて（重要な制約）

このセッションの環境は組織のegressポリシーで、学術系ドメイン
（pmc.ncbi.nlm.nih.gov / mdpi.com / frontiersin.org / scholar.google.com /
semanticscholar.org / researchgate.net / pubmed.ncbi.nlm.nih.gov）への
アウトバウンド接続がプロキシ側で一律ブロックされている（`curl`直叩きでも
`CONFIG_error connect tunnel failed, response 403`、WebFetchツールでも同じ403）。
これは特定サイトのbot対策ではなく**環境のネットワークポリシーそのもの**なので、
検索手段（WebSearch/hermes-relay等）を変えても同じ壁にあたる。WebSearchの
検索結果スニペット経由の情報しか得られない。

## 保留にした理由（citation_statusを全体では変えていない理由）

1. **角度の符号規約が情報源ごとに不明瞭**：文献は「屈曲角度」（伸展位=0°、曲がるほど増加）で
   報告することが多いが、本アプリの `joint_angle` プリミティブは「関節がなす角」
   （伸展位=180°、曲がるほど減少）を返す。スポーツバイオメカニクスでの一般的な
   goniometric conventionに基づき `180 - flexion` で変換して反映したが、
   各論文の実際の定義は本文を読めておらず確証はない。
2. **イベント定義の対応関係が未検証**：文献の「cocking phase」等が、本アプリの
   detectors.py（serve_like: toss_apex/trophy/impact）の検出フレームと
   厳密に対応するとは限らない。

`line_separation`系（捻転差）は回旋の角度差そのものであり上記1の変換問題が
無いため、joint_angle系（膝・肘の屈曲/伸展）より相対的に信頼度が高い。

## 反映済み（shot-mechanics.v1.yaml内のsourceフィールドに詳細あり）

| ショット | 指標 | 反映した値 | 元の報告値 | 変換 | 出典 |
|---|---|---|---|---|---|
| serve | knee_flexion_at_trophy | [106, 125]°, tol 10 | 前膝屈曲 64.5±9.7° | 180-flexion、±1SD | Frontiers Sports Act Living (2024) 系統的レビュー・メタ分析 |
| serve | shoulder_hip_separation_at_trophy | [15, 30]°, tol 8 | cocking位で約20°（単一点推定） | 変換不要（回旋差） | 同上 |
| serve | elbow_extension_at_impact | [134, 166]°, tol 12 | インパクト時肘屈曲 30.1±15.9° | 180-flexion、±1SD | 同上 |
| forehand | shoulder_hip_separation_at_backswing | [18, 30]°, tol 6 | バックスイング終盤：上級者20.44°/一般15.79°（P=0.029） | 変換不要（回旋差） | "Biomechanical model of forehand stroke of tennis players"（ResearchGate、3D動作解析） |

いずれも `citation_status` は据え置き（`placeholder_pending_literature_review`）。
UI/LLM側の「参考値（検証中）」表記は変更していない — 本文未確認のjoint_angle変換を
含むため、上記の反映は「プレースホルダーより実データに近い暫定値」という位置づけ。

## 未着手（引き続きplaceholderのまま）

- serve: elbow_height_at_trophy, contact_height_relative, toss_apex_to_impact_ms
- forehand: contact_forward_of_hip, contact_height_relative, backswing_to_contact_ms, elbow_angle_at_contact
- backhand: 全指標（文献検索未実施。特に両手/片手のスタイル別数値）
- smash: 全指標（サーブの値を流用できる可能性はあるが未検討）
- volley: 全指標（設計時点の想定どおり文献自体が薄い見込み）

参考として見つかったが本アプリの指標に未対応の値（将来の指標追加候補）：
サーブインパクト時の肩挙上角 110.7±16.9°、体幹前傾（水平基準）約48°
（いずれもFrontiers 2024メタ分析）。

## 次のアクション（引き継ぎ用）

1. 上記出典のPDF本文（機関アクセス・購入・著者への問い合わせ等）を入手し、
   角度の符号規約・測定フレーム定義を確認する。このセッションの環境からは
   到達不能（上記「本文PDFアクセスについて」参照）。
2. 確認できた指標から `elite_range`/`tolerance`/`source` を再調整し、
   `citation_status` を該当ショットだけ `verified` 等に細分化する
   （現状は全ショット共通の1フラグなので、指標単位・ショット単位に分ける設計変更が必要）。
3. コーチ・理学療法士等のドメイン専門家によるサニティチェックを推奨（06 §リスクまとめの
   「誤った指導リスク」対応として、文献値だけでなく実務者の確認を挟む）。
4. backhand/smash/volleyの文献調査は未着手。
