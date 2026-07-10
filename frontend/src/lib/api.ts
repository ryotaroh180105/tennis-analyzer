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

export const STATUS_LABEL_JA: Record<MatchStatus, string> = {
  queued: "動画を確認しています",
  prechecking: "動画を確認しています",
  ingesting: "動画を整えています（1/3）",
  analyzing: "プレーを探しています（2/3）",
  editing: "編集しています（3/3）",
  done: "完了",
  failed: "解析できませんでした",
};
