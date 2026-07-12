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
  confidence: number | null;
}

// 11 §58: confidence < 0.7 は低信頼（彩度低下＋波線ハンドル、Ribbon.tsx）。
// ユーザーが直接編集した区間はconfidence=nullで低信頼扱いにしない。
export const LOW_CONFIDENCE_THRESHOLD = 0.7;

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
    apiFetch<{ playlist_url: string; thumbnail_url: string | null; segments: SegmentEffective[] | null }>(
      `/api/matches/${matchId}/playback`
    ),
  getSharePlayback: (token: string) =>
    apiFetch<{ playlist_url: string; thumbnail_url: string | null; segments: SegmentEffective[] | null }>(
      `/api/share/${token}/playback`
    ),

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

export interface SwingMetricValue {
  id: string;
  value: number | null;
  confidence: number;
}

export interface Swing {
  t: number;
  metrics: Record<string, SwingMetricValue>;
}

export interface FormAnalysisResult {
  shot_type: FormShotType;
  dominant_side: string;
  swing_count: number;
  insufficient_data: boolean;
  swings: Swing[];
  metrics: FormMetric[];
  feedback_metrics: string[];
  confidence: { pose_detection_ratio: number };
  citation_status: string;
  created_at: string;
}

// UI文言はロケールキー型辞書に集約している（13 E'）。既存の import 元を変えずに
// 済むよう、ここで再エクスポートする。
export {
  STATUS_LABEL_JA,
  FORM_STATUS_LABEL_JA,
  FORM_SHOT_TYPE_LABEL_JA,
  BACKHAND_STYLE_LABEL_JA,
  FORM_PHASE_LABEL_JA,
  FORM_METRIC_LABEL_JA,
  FORM_METRIC_STATUS_LABEL_JA,
  MATCH_FAILURE_LABEL_JA,
  PRECHECK_WARNING_LABEL_JA,
} from "@/lib/i18n/dictionaries";
