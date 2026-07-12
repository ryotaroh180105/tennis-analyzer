export type MatchStatus =
  | "queued"
  | "prechecking"
  | "ingesting"
  | "analyzing"
  | "editing"
  | "done"
  | "failed";

export interface MatchAsset {
  kind: string;
  generation: number;
  duration_s: number | null;
}

export interface Match {
  id: string;
  title: string;
  status: MatchStatus;
  failure_reason: { code: string; message: string } | null;
  preflight_report: { degraded: boolean; checks: Record<string, any> } | null;
  self_side: "near" | "far" | null;
  assets: MatchAsset[];
  progress: { stage: string | null; pct: number };
  created_at: string;
}

export interface SegmentEffective {
  start_s: number;
  end_s: number;
}

export interface SegmentsResponse {
  revision: number;
  effective: SegmentEffective[];
  raw: Array<{
    id: string;
    revision: number;
    op: string;
    base_segment_id: string | null;
    start_s: number | null;
    end_s: number | null;
    source: string;
  }>;
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  listMatches: () => apiFetch<Match[]>("/api/matches"),
  getMatch: (id: string) => apiFetch<Match>(`/api/matches/${id}`),
  setSelfSide: (id: string, selfSide: "near" | "far") =>
    apiFetch<Match>(`/api/matches/${id}/self-side`, {
      method: "PATCH",
      body: JSON.stringify({ self_side: selfSide }),
    }),
  createMatch: (uploadId: string, title: string) =>
    apiFetch<{ id: string; status: string }>("/api/matches", {
      method: "POST",
      body: JSON.stringify({ upload_id: uploadId, title }),
    }),
  getSegments: (matchId: string) => apiFetch<SegmentsResponse>(`/api/matches/${matchId}/segments`),
  patchSegments: (
    matchId: string,
    baseRevision: number,
    ops: Array<{ op: string; base_segment_id?: string; start_s?: number; end_s?: number }>
  ) =>
    apiFetch<SegmentsResponse>(`/api/matches/${matchId}/segments`, {
      method: "PATCH",
      body: JSON.stringify({ base_revision: baseRevision, ops }),
    }),
  recut: (matchId: string) => apiFetch<{ status: string }>(`/api/matches/${matchId}/recut`, { method: "POST" }),
  createShare: (matchId: string) => apiFetch<{ url: string }>(`/api/matches/${matchId}/share`, { method: "POST" }),
  getPlayback: (matchId: string) =>
    apiFetch<{ playlist_url: string; thumbnail_url: string | null }>(`/api/matches/${matchId}/playback`),
  getSharePlayback: (token: string) =>
    apiFetch<{ playlist_url: string; thumbnail_url: string | null }>(`/api/share/${token}/playback`),

  // アップロード（マルチパート・中断再開。10 §アップロードAPI）
  createUpload: (filename: string, totalSize: number, contentType: string) =>
    apiFetch<{ upload_id: string; part_size: number }>("/api/uploads", {
      method: "POST",
      body: JSON.stringify({ filename, total_size: totalSize, content_type: contentType }),
    }),
  getPartUrls: (uploadId: string, partNumbers: number[]) =>
    apiFetch<{ urls: Record<string, string> }>(`/api/uploads/${uploadId}/parts`, {
      method: "POST",
      body: JSON.stringify({ part_numbers: partNumbers }),
    }),
  getUploadStatus: (uploadId: string) =>
    apiFetch<{ status: string; completed_parts: Array<{ part_number: number }> }>(
      `/api/uploads/${uploadId}`
    ),
  completeUpload: (uploadId: string) =>
    apiFetch<void>(`/api/uploads/${uploadId}/complete`, { method: "POST" }),

  // スコア半自動入力（10 §API契約 / 01 §Phase1: 自動判定はせずワンタップ入力）
  getScore: (matchId: string) => apiFetch<ScoreResponse>(`/api/matches/${matchId}/score`),
  addScorePoint: (matchId: string, winner: "self" | "opponent") =>
    apiFetch<ScoreResponse>(`/api/matches/${matchId}/score/points`, {
      method: "POST",
      body: JSON.stringify({ winner }),
    }),
  undoScorePoint: (matchId: string) =>
    apiFetch<ScoreResponse>(`/api/matches/${matchId}/score/points/last`, { method: "DELETE" }),

  // ミス分類スタッツ・ハイライト（04-miss-taxonomy.md / 01 §Phase1）
  getStats: (matchId: string) => apiFetch<StatsResponse>(`/api/matches/${matchId}/stats`),
  generateHighlight: (matchId: string) =>
    apiFetch<{ status: string }>(`/api/matches/${matchId}/highlight`, { method: "POST" }),
  getHighlightPlayback: (matchId: string) =>
    apiFetch<{ playlist_url: string; thumbnail_url: string | null }>(`/api/matches/${matchId}/highlight/playback`),

  // 即時フィードバック（07-advice-delivery.md §①。解析完了後に非同期生成される）
  getFeedback: (matchId: string) => apiFetch<FeedbackResponse>(`/api/matches/${matchId}/feedback`),

  // フォーム解析（Phase 3拡張。12-form-analysis.md）
  createFormSession: (uploadId: string, title: string, shotType: FormShotType, backhandStyle?: BackhandStyle) =>
    apiFetch<FormSession>("/api/form-sessions", {
      method: "POST",
      body: JSON.stringify({
        upload_id: uploadId,
        title,
        shot_type: shotType,
        backhand_style: backhandStyle ?? null,
      }),
    }),
  listFormSessions: () => apiFetch<FormSession[]>("/api/form-sessions"),
  getFormSession: (id: string) => apiFetch<FormSession>(`/api/form-sessions/${id}`),
  getFormAnalysis: (id: string) => apiFetch<FormAnalysisResult>(`/api/form-sessions/${id}/analysis`),
};

export interface ScoreResponse {
  completed_sets: Array<{ self: number; opponent: number }>;
  current_set_games: { self: number; opponent: number };
  current_game: { self: number; opponent: number };
  current_game_display: { self: string; opponent: string } | null;
  tiebreak: { self: number; opponent: number } | null;
  match_winner: "self" | "opponent" | null;
  total_points: number;
}

export interface StatsHighlight {
  point_index: number;
  start_s: number | null;
  end_s: number | null;
  label: string | null;
  importance: string;
  tags: string[];
}

export interface StatsLabelCount {
  label: string;
  importance: string;
  count: number;
}

export interface StatsResponse {
  total_points: number;
  unclassified_points: number;
  stat_counts: Record<string, number>;
  labels: StatsLabelCount[];
  highlights: StatsHighlight[];
}

export interface FeedbackResponse {
  summary: string;
  tendencies: string[];
  drill_suggestions: string[];
  created_at: string;
}

export type FormSessionStatus = "queued" | "analyzing" | "done" | "failed";
export type FormShotType = "serve" | "forehand" | "backhand" | "smash" | "volley";
export type BackhandStyle = "one_handed" | "two_handed" | "auto";

export interface FormSession {
  id: string;
  title: string;
  shot_type: FormShotType;
  backhand_style: BackhandStyle | null;
  status: FormSessionStatus;
  failure_reason: { code: string; message: string } | null;
  duration_s: number | null;
  created_at: string;
}

export interface FormMetric {
  id: string;
  phase: string;
  unit: string;
  measured: number | null;
  iqr: number | null;
  elite_range: [number, number] | null;
  expected_sign: "positive" | "negative" | null;
  status: "in_range" | "borderline" | "out_of_range" | "unknown" | "measured";
  high_variance: boolean;
  valid_swings: number;
  advice_key: string;
}

export interface FormAnalysisResult {
  shot_type: FormShotType;
  dominant_side: string;
  swing_count: number;
  insufficient_data: boolean;
  metrics: FormMetric[];
  feedback_metrics: string[];
  confidence: { pose_detection_ratio: number };
  citation_status: string;
  created_at: string;
}

export const STATUS_LABEL_JA: Record<MatchStatus, string> = {
  queued: "動画を確認しています",
  prechecking: "動画を確認しています",
  ingesting: "動画を整えています（1/3）",
  analyzing: "プレーを探しています（2/3）",
  editing: "編集しています（3/3）",
  done: "完了",
  failed: "解析できませんでした",
};

export const FORM_STATUS_LABEL_JA: Record<FormSessionStatus, string> = {
  queued: "解析を待っています",
  analyzing: "骨格を解析しています",
  done: "完了",
  failed: "解析できませんでした",
};

export const FORM_SHOT_TYPE_LABEL_JA: Record<FormShotType, string> = {
  serve: "サーブ",
  forehand: "フォアハンド",
  backhand: "バックハンド",
  smash: "スマッシュ",
  volley: "ボレー",
};

export const BACKHAND_STYLE_LABEL_JA: Record<BackhandStyle, string> = {
  one_handed: "片手",
  two_handed: "両手",
  auto: "自動判定",
};

export const FORM_PHASE_LABEL_JA: Record<string, string> = {
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
};

export const FORM_METRIC_LABEL_JA: Record<string, string> = {
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
};

export const FORM_METRIC_STATUS_LABEL_JA: Record<FormMetric["status"], string> = {
  in_range: "参考レンジ内",
  borderline: "レンジにやや近い",
  out_of_range: "参考レンジ外",
  unknown: "測定不能（映り込み不足）",
  measured: "測定値のみ（参考レンジ未確立）",
};
