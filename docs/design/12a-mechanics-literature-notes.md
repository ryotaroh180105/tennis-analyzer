# 12a. shot-mechanics.v1.yaml 文献レビュー：調査結果

タスク#26の調査結果。**PubMed MCPコネクタ接続後（2026-07-11）、serveの3指標を
本文確認済みの値に更新した**。以下は最新の状態。

## 経緯

1. 当初WebSearchのスニペットのみで4指標を暫定反映（角度の符号規約・出典の
   厳密な特定ができず、精度に限界があった）
2. このセッションの`curl`/`WebFetchツール`は学術ドメインを含む一般Web閲覧が
   ブロックされていることを確認（Wikipediaでも403を再現。環境のネットワーク
   ポリシーそのもので、hermes-relayやHaikuサブエージェント等の検索手段を
   変えても回避できない）
3. `SearchMcpRegistry`でPubMed MCPコネクタ（`authless: true`）を発見。
   `claude.ai`の接続設定で有効化してもらい、`get_full_text_article`で
   本文取得に成功（MCP経由はこのセッションのネットワーク制約を受けない）
4. 本文を読み、**角度の符号規約を明示的に確認**（Methods章に "According to
   the ISB convention, all angles are defined as zero in the anatomical
   reference position" と明記）。当初の暫定反映で使っていた
   `180 - flexion` 変換の妥当性が裏付けられた
5. 併せて、当初のWebSearchスニペットからの引用に**誤り**（実際には論文が
   報告していない数値を別の一般的な検索結果と混同していたケース）が
   1件見つかり修正した

## 確認済み（shot-mechanics.v1.yaml反映済み。詳細・原文抜粋はsourceフィールド参照）

| ショット | 指標 | 値 | 出典 | 確度 |
|---|---|---|---|---|
| serve | knee_flexion_at_trophy | [106, 125]°, tol 10 | Jacquier-Bret & Gorce, Front Sports Act Living 2024, PMID 39040663 / PMC11260724（27研究のメタ分析） | **高**（本文確認・ISB規約明記・他2文献の引用範囲とも整合） |
| serve | shoulder_hip_separation_at_trophy | [23, 34]°, tol 8 | 同著者, Sensors 2024 (PMID 38894086/PMC11175047) と Front Sports Act Living 2024 (PMID 39444495/PMC11496077)。いずれも先行individual研究群を引用 | **高**（本文確認・回旋差のため符号規約問題なし・8件の個別研究値が23〜34°に集中） |
| serve | elbow_extension_at_impact | [141, 161]°, tol 12 | PMC11260724（外れ値研究除外後の精緻化値29.2±9.9°を採用、著者らが"more relevant"と明記） | **高**（本文確認） |
| forehand | shoulder_hip_separation_at_backswing | [18, 30]°, tol 6 | "Biomechanical model of forehand stroke of tennis players" (ResearchGate) | **中**（PubMed非索引ジャーナルのためPubMed MCPでは再検証できず。WebSearchスニペットのみ） |

### 修正した誤り

初回反映時、`shoulder_hip_separation_at_trophy` を「Frontiers 2024メタ分析で
cocking位約20°」として反映していたが、**本文確認の結果、このメタ分析は
shoulder-hip separation angleを実際には報告していない**ことが判明した
（メタ分析の対象は trunk inclination / front knee / back knee flexion /
shoulder lateral rotation / shoulder elevation / elbow flexion の6指標のみ）。
別の一般的なWebSearch要約と誤って結び付けていた。今回、同著者の別2論文
（PMC11175047, PMC11496077）が引用する個別研究群（8件、23〜34°に集中）に
基づいて正しい出典で反映し直した。

## citation_statusを全体では変更していない理由

serveの3指標は個別に高確度だが、以下が残るため`citation_status`は
全体としては`placeholder_pending_literature_review`のまま据え置いている：

1. 指標単位・ショット単位での細分化フラグが未実装（現状は1ファイル1フラグ）
2. forehand以下・backhand/smash/volleyは依然未検証
3. 文献側のフェーズ定義（例: "trophy position" = "elbow lowest vertical
   position and maximum knee flexion"）と本アプリのdetectors.py側の検出
   フレーム定義の対応関係は、概念的な一致は確認したが、実際のCV出力との
   ズレは未検証（合成データでのユニットテストのみ）

## 未着手（引き続きplaceholderのまま）

- serve: elbow_height_at_trophy, contact_height_relative, toss_apex_to_impact_ms
- forehand: contact_forward_of_hip, contact_height_relative, backswing_to_contact_ms, elbow_angle_at_contact
- backhand: 全指標
- smash: 全指標（PubMedで"tennis overhead smash kinematics"を検索したが該当0件。
  文献自体が薄いという設計時点の想定どおり。サーブの値を流用できる可能性はあるが、
  それは"smash固有の文献値"と偽ることになるため未反映）
- volley: 全指標（設計時点の想定どおり文献自体が薄い見込み。未検索）

### 見つかったが本アプリの指標に未対応の値（将来の指標追加候補）

いずれもPMC11260724のメタ分析より、本文確認済み：
- サーブトロフィー位置の体幹前傾: 25.0±7.1°
- サーブRLP（racket low point）の肩外旋: 130.1±26.5°
- サーブインパクト時の肩挙上角: 110.7±16.9°（外れ値除外後: 104.6±6.1°）

### backhand調査の手がかり（未確認）

"The Kinematics of Trunk and Upper Extremities in One-Handed and Two-Handed
Backhand Stroke"（PMC3588639）をPubMed MCPで全文取得済み。**分離角の符号規約
（片手=positive、両手=negative、コンタクト時に測定）は本文で確認できたが、
具体的な度数の数値は図表のみに記載されておりテキスト抽出には含まれていな
かった**。数値抽出には別途図表の解析が必要（未実施）。またこの論文の測定
タイミングは「コンタクト時」であり、現行YAMLのbackhand指標（`backswing_end`
時点）とは異なる点に注意。

## 今後の文献調査で使えるツール（2026-07-11判明、恒久メモ）

- **PubMed MCPコネクタ**（`authless: true`）— 医学・生命科学・スポーツ科学系。
  `get_full_text_article`でPMC収録論文の全文を取得できる。このセッションの
  `curl`/`WebFetch`ブロックを回避できることを実証済み。今後の同種タスクは
  まずこれを使う
- **Elicit**（OAuth要）— 分野を問わない学術論文検索・要約。PubMed非対応領域
  （工学・社会科学等）で有用
- 上記いずれも書籍（コーチング教本等）は対象外。別問題として残る

## 次のアクション（引き継ぎ用）

1. backhand: PMC3588639の図表から分離角の数値を読み取る（テキスト抽出では
   取得不可、別アプローチが必要）。PubMedで追加の片手/両手比較論文を検索する
2. smash: サーブの値を流用するか、"文献なし"のまま`citation_status`を
   ショット単位で正直に表示する設計にするか判断する
3. volley: 未検索。PubMedで"tennis volley kinematics"等を試す
4. `citation_status`の指標単位・ショット単位への細分化（スキーマ変更）を検討する
5. コーチ・理学療法士等のドメイン専門家によるサニティチェックを推奨（06 §リスク
   まとめの「誤った指導リスク」対応）
