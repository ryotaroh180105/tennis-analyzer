# 12a. shot-mechanics.v1.yaml 文献レビュー：調査結果

タスク#26の調査結果。**PubMed MCPコネクタ接続後（2026-07-11）、serveの3指標を
本文確認済みの値に更新し、backhandの1指標を定性評価（符号のみ）として追加した**。
以下は最新の状態。

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

## 追加調査（PubMed MCP、backhand/smash/volley対象。2026-07-11）

PubMed MCPが使えるようになったので、backhand/smash/volleyも通しで検索した。
結論：**数値として反映できる新しい成果は無かった**。以下、探索の記録（次回の
やり直しを防ぐため）。

- **backhand**: `PMC4306773`（Genevois et al., "Performance Factors Related to
  the Different Tennis Backhand Groundstrokes: A Review", J Sports Sci Med,
  PMID 25729308）— 61論文を統合したレビューで理想的な情報源のはずだったが、
  `get_full_text_article`で本文が空文字列で返る（アブストラクトのみ取得可能。
  ジャーナル側のフォーマットがコネクタでパースできない可能性）。アブストラクト
  自体は定性的な結論（両手打ちは体幹回旋依存・片手打ちは上肢の分節回旋依存）
  のみで、度数の数値は含まれない。追加で "elbow extension impact degrees",
  "pelvis rotation contact point" 等のクエリも試したが0件
- **smash**: "tennis overhead smash kinematics/biomechanics" 系のクエリを
  2パターン試したが、関連論文0件（1件だけヒットしたのはIMUでのショット分類の
  論文で角度データなし）。設計時点の想定どおり、tennis smash固有の運動学文献は
  PubMedに実質存在しない
- **volley**: "tennis volley stroke kinematics biomechanics" で6件ヒットしたが、
  関連性があるのはChow et al. 1999（"Movement characteristics of the tennis
  volley", PMID 10378913）のみ。これも地面反力・反応時間・ストローク時間
  （381〜803ms）の研究で、肘角度変化・膝屈曲・打点位置という現行YAMLの指標には
  対応しない。他はIMUでのショット分類・クレアチンサプリの研究で無関係

以上より、backhand/smash/volleyの`elite_range`は**引き続きplaceholderのまま**
とする。捏造や弱い出典での穴埋めより、正直にplaceholderとして残す方針を維持
（不変原則1）。

### backhand調査の手がかり（→ 定性評価として反映済み）

"The Kinematics of Trunk and Upper Extremities in One-Handed and Two-Handed
Backhand Stroke"（PMC3588639）をPubMed MCPで全文取得済み。**分離角の符号規約
（片手=positive、両手=negative、コンタクト時に測定）は本文で確認できたが、
具体的な度数の数値は図表のみに記載されておりテキスト抽出には含まれていな
かった**。数値抽出には別途図表の解析が必要（未実施・引き続き手詰まり）。

ユーザー指示（「定性的でもいいよ、とにかく評価ができればいい」）を受け、
数値レンジの代わりに**符号（向き）のみの定性評価**として反映した：

- `config/shot-mechanics.v1.yaml` の `backhand.metrics` に
  `shoulder_hip_separation_direction_at_contact`（one_handed想定、
  `expected_sign: positive`）と `_2h`（two_handed想定、`expected_sign: negative`）
  を追加。`primitive: line_separation_signed`（新規プリミティブ、`abs()`を
  取らない符号付き回旋差。`cv-worker/cvpipeline/pose/primitives.py`）
- 指標エンジン（`cvpipeline/pose/metrics_engine.py`）に定性評価モードを追加。
  `expected_sign`ありの指標は`elite_range`を持たず（`None`）、中央値の符号が
  一致すれば`in_range`、不一致なら`out_of_range`。ばらつき判定
  （`high_variance`）はスイング間で符号が割れているかどうかで判定する
  （IQR/中央値比ではなく）
- API（`backend/app/api/schemas.py`）・フロント（`frontend/src/lib/api.ts`,
  `frontend/src/app/form/[id]/page.tsx`）を`elite_range`がnullでも
  レンダリングできるよう修正（定性指標は「正の値が理想」のようなテキスト表示）
- 測定タイミングの注意点：この論文の計測は「コンタクト時」。現行YAMLの本指標
  も`at: contact`で追加しており、他のbackhand指標（`backswing_end`時点のもの）
  とは測定フェーズが異なる点に留意

`citation_status`は`accuracy: 中`相当（方向性は本文確認済みだが、度数の
数値的な裏付けは無い）。テストは
`cv-worker/tests/test_pose_primitives.py`・`test_pose_metrics_engine.py`・
`test_pose_orchestrator.py`に追加済み。

### smash / volley — 定性評価も含めて反映できる知見は無し

同じ基準（数値でなくても方向性の主張があれば反映）でsmash/volleyの既存調査
結果を見直したが、**現行YAMLの指標（肘角度・分離角・打点位置）に対応する
定性的な主張すら見つからなかった**：

- smash: PubMed該当論文0件（前回調査のまま。文献自体が存在しない）
- volley: Chow et al. 1999は地面反力・反応時間・ストローク時間の研究であり、
  肘角度変化・膝屈曲・打点位置について「正/負」「大きい/小さい」のような
  比較言及すら本文に無い

このため、smash/volleyの指標は引き続き完全なplaceholder（`elite_range`も
`expected_sign`も設定なし）のまま据え置く。捏造や無関係な文献の転用より
「評価しない」ことを選ぶのは不変原則1どおりの判断（データ自体は表示され、
レンジ比較・方向性評価のみ行わない設計。12 §ロールアウト3dで想定済みの
フォールバック）。

## 今後の文献調査で使えるツール（2026-07-11判明、恒久メモ）

- **PubMed MCPコネクタ**（`authless: true`）— 医学・生命科学・スポーツ科学系。
  `get_full_text_article`でPMC収録論文の全文を取得できる。このセッションの
  `curl`/`WebFetch`ブロックを回避できることを実証済み。今後の同種タスクは
  まずこれを使う
- **Elicit**（OAuth要）— 分野を問わない学術論文検索・要約。PubMed非対応領域
  （工学・社会科学等）で有用
- 上記いずれも書籍（コーチング教本等）は対象外。別問題として残る

## 次のアクション（引き継ぎ用）

1. backhand: 定性評価（符号のみ）として反映済み（上記セクション参照）。
   PMC3588639の図表から実際の度数を読み取れれば、`expected_sign`を
   `elite_range`に格上げできる（図表は画像解析が必要、未着手）。
   PMC4306773は本文取得できず（コネクタ側の既知の限界、変わらず）
2. smash: PubMed検索で該当0件（定性的な主張も含めて無し、確認済み）。
   サーブの値を流用するか、"文献なし"のまま`citation_status`をショット単位で
   正直に表示する設計にするか判断する
3. volley: PubMed検索で該当する角度データ・定性的主張ともに0件（確認済み）。
   文献ベースでの裏取りは実質的に手詰まり。レンジ比較・方向性評価なし・
   測定値のみ表示（12 §ロールアウト3dで想定済みのフォールバック）を採用
4. `citation_status`の指標単位・ショット単位への細分化（スキーマ変更）を検討する
   （定性/定量の別も含めて。現状はファイル全体で1フラグのまま）
5. コーチ・理学療法士等のドメイン専門家によるサニティチェックを推奨（06 §リスク
   まとめの「誤った指導リスク」対応）
