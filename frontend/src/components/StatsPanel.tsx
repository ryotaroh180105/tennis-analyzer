"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { VideoPlayer } from "@/components/VideoPlayer";

export function StatsPanel({ matchId }: { matchId: string }) {
  const { data: stats } = useSWR(["stats", matchId], () => api.getStats(matchId));
  const [generating, setGenerating] = useState(false);

  const { data: highlightPlayback } = useSWR(
    ["highlight-playback", matchId],
    () => api.getHighlightPlayback(matchId).catch(() => null),
    { refreshInterval: (data) => (data ? 0 : generating ? 4000 : 0) }
  );

  if (!stats) return null;

  const classified = stats.total_points - stats.unclassified_points;

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await api.generateHighlight(matchId);
    } catch {
      setGenerating(false);
    }
  };

  return (
    <div style={{ padding: "10px 16px" }}>
      <div
        style={{
          fontSize: 10,
          color: "var(--ink-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          marginBottom: 6,
        }}
      >
        ミス分類（試験運用）
      </div>

      <p style={{ fontSize: 11, color: "var(--ink-secondary)", margin: "0 0 8px" }}>
        {stats.total_points}ポイント中 {classified}件を分類（未分類 {stats.unclassified_points}件）
      </p>

      {stats.labels.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
          {stats.labels.map((l) => (
            <div key={l.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
              <span>{l.label}</span>
              <span style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{l.count}</span>
            </div>
          ))}
        </div>
      )}

      {highlightPlayback ? (
        <div style={{ marginTop: 4, aspectRatio: "16/10" }}>
          <VideoPlayer playlistUrl={highlightPlayback.playlist_url} thumbnailUrl={highlightPlayback.thumbnail_url} />
        </div>
      ) : stats.highlights.length > 0 ? (
        <button
          onClick={handleGenerate}
          disabled={generating}
          style={{
            width: "100%",
            padding: 10,
            borderRadius: 8,
            border: "none",
            background: "var(--sand)",
            color: "#fff",
            fontSize: 12,
            fontWeight: 700,
          }}
        >
          {generating ? "作成中…" : `ハイライトを作る（候補${stats.highlights.length}件）`}
        </button>
      ) : (
        <p style={{ fontSize: 11, color: "var(--ink-secondary)", margin: 0 }}>
          まだハイライト候補がありません
        </p>
      )}
    </div>
  );
}
