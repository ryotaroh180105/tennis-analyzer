// UI文言のロケールキー型辞書（設計方針7・11 §149「文言はすべて users.locale から引く辞書化」）。
//
// config/taxonomy.v1.yaml・advice-rules.v1.yaml と同じ「ロケールキー→値」の構造をフロントにも
// 導入し、UI文言が個々のコンポーネント/ページに散らばっていた状態（13 E'）を解消する。
//
// スコープの注記：現状ロケールは 'ja' のみが実際に必要とされている（他言語展開の具体的な
// 計画は無い）ため、ページ内の個々のJSXリテラル文言まで全て辞書化はしていない
// （YAGNI：使われない多言語化のためにリスクの高い機械的な全文置換をする理由が無い）。
// ここに集約したのは既存の「共有される語彙」（ステータス・ラベル・エラーメッセージの
// レコード型辞書）— これらは元々複数箇所から参照される設計だったため、ロケールキー化の
// 実利益（第2言語追加時にこのファイルだけ拡張すればよい）が最も大きい。

import type { BackhandStyle, FormMetric, FormSessionStatus, FormShotType, MatchStatus } from "@/lib/api";

export type Locale = "ja";

interface Dictionary {
  status: Record<MatchStatus, string>;
  formStatus: Record<FormSessionStatus, string>;
  formShotType: Record<FormShotType, string>;
  backhandStyle: Record<BackhandStyle, string>;
  formPhase: Record<string, string>;
  formMetric: Record<string, string>;
  formMetricStatus: Record<FormMetric["status"], string>;
  matchFailure: Record<string, string>;
  precheckWarning: Record<string, string>;
}

const ja: Dictionary = {
  status: {
    queued: "動画を確認しています",
    prechecking: "動画を確認しています",
    ingesting: "動画を整えています（1/3）",
    analyzing: "プレーを探しています（2/3）",
    editing: "編集しています（3/3）",
    done: "完了",
    failed: "解析できませんでした",
  },

  formStatus: {
    queued: "解析を待っています",
    analyzing: "骨格を解析しています",
    done: "完了",
    failed: "解析できませんでした",
  },

  formShotType: {
    serve: "サーブ",
    forehand: "フォアハンド",
    backhand: "バックハンド",
    smash: "スマッシュ",
    volley: "ボレー",
  },

  backhandStyle: {
    one_handed: "片手",
    two_handed: "両手",
    auto: "自動判定",
  },

  formPhase: {
    preparation: "構え",
    toss: "トス",
    point: "ポインティング",
    trophy: "トロフィーポーズ",
    acceleration: "加速",
    impact: "インパクト",
    follow_through: "フォロースルー",
    ready: "構え",
    backswing_end: "バックスイング",
    contact: "コンタクト",
    punch_start: "パンチ開始",
    // smash: point_arm_apex_height はserve_like検出器のtoss_apexイベントを
    // 「ポインティング腕の頂点」として読み替える（shot-mechanics.v1.yaml参照）
    toss_apex: "ポインティング",
  },

  formMetric: {
    // serve / smash
    knee_flexion_at_trophy: "トロフィーポーズの膝の曲がり",
    elbow_height_at_trophy: "トロフィーポーズの肘の高さ",
    shoulder_hip_separation_at_trophy: "肩と腰の捻転差",
    elbow_extension_at_impact: "インパクト時の肘の伸び",
    contact_height_relative: "打点の高さ",
    toss_apex_to_impact_ms: "トスからインパクトまでの時間",
    point_arm_apex_height: "ポインティング腕の高さ",
    // forehand / backhand
    shoulder_hip_separation_at_backswing: "バックスイングの捻転差",
    shoulder_hip_separation_at_backswing_2h: "バックスイングの捻転差",
    contact_forward_of_hip: "打点の前後位置",
    backswing_to_contact_ms: "バックスイングからコンタクトまでの時間",
    elbow_angle_at_contact: "コンタクト時の肘の角度",
    elbow_extension_at_contact: "コンタクト時の肘の伸び",
    shoulder_hip_separation_direction_at_contact: "コンタクト時の捻転の向き",
    shoulder_hip_separation_direction_at_contact_2h: "コンタクト時の捻転の向き",
    // volley
    elbow_angle_delta_through_contact: "コンタクト前後の肘角度変化",
    contact_forward_of_body: "打点の前後位置",
    knee_flexion_at_contact: "コンタクト時の膝の曲がり",
  },

  formMetricStatus: {
    in_range: "参考レンジ内",
    borderline: "レンジにやや近い",
    out_of_range: "参考レンジ外",
    unknown: "測定不能（映り込み不足）",
    measured: "測定値のみ（参考レンジ未確立）",
  },

  matchFailure: {
    input_invalid: "動画を読み込めませんでした。別の動画でお試しください。",
    analyze_error: "解析中にエラーが発生しました。",
    edit_error: "編集中にエラーが発生しました。",
    retry_exhausted: "解析に繰り返し失敗しました。動画を確認してもう一度お試しください。",
  },

  precheckWarning: {
    resolution: "解像度が720p未満です。精度が下がる場合があります。",
    framerate: "フレームレートが24fps未満です。精度が下がる場合があります。",
    orientation: "縦向きの動画です。画角が狭く、映り込みが不足する場合があります。",
    court: "コートの検出信頼度が低めです。区間の精度をご確認ください。",
    coverage: "コート全体が画角に収まっていない可能性があります。精度が下がる場合があります。",
    stability: "カメラのブレが大きいようです。精度が下がる場合があります。",
    brightness: "映像が暗いか逆光のようです。精度が下がる場合があります。",
  },
};

const DICTIONARIES: Record<Locale, Dictionary> = { ja };

// 現状フロントはUser.localeを取得していない（バックエンドのUser.localeは今のところ通知文面
// 生成にのみ使われている）ため、暫定的に既定ロケール固定とする。ロケール切替UIを追加する際は
// ここを差し替える。
const DEFAULT_LOCALE: Locale = "ja";

export function getDictionary(locale: Locale = DEFAULT_LOCALE): Dictionary {
  return DICTIONARIES[locale];
}

const dict = getDictionary();

export const STATUS_LABEL_JA = dict.status;
export const FORM_STATUS_LABEL_JA = dict.formStatus;
export const FORM_SHOT_TYPE_LABEL_JA = dict.formShotType;
export const BACKHAND_STYLE_LABEL_JA = dict.backhandStyle;
export const FORM_PHASE_LABEL_JA = dict.formPhase;
export const FORM_METRIC_LABEL_JA = dict.formMetric;
export const FORM_METRIC_STATUS_LABEL_JA = dict.formMetricStatus;
export const MATCH_FAILURE_LABEL_JA = dict.matchFailure;
export const PRECHECK_WARNING_LABEL_JA = dict.precheckWarning;
