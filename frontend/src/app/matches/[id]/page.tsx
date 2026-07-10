"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { api, STATUS_LABEL_JA } from "@/lib/api";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { Ribbon } from "@/components/Ribbon";
import { ScorePad } from "@/components/ScorePad";
import { StatsPanel } from "@/components/StatsPanel";
import { VideoPlayer } from "@/components/VideoPlayer";

function estimateRemainingMs(createdAt: string, pct: number): number | null {
  if (pct <= 0) return null;
  const elapsedMs = Date.now() - new Date(createdAt).getTime();
  if (elapsedMs <= 0) return null;
  const totalMs = elapsedMs / (pct / 100);
  return Math.max(totalMs - elapsedMs, 0);
}

function formatRemaining(ms: number): string {
  const totalMin = Math.round(ms / 60000);
  if (totalMin < 1) return "まもなく完了";
  if (totalMin < 60) return `残り目安 ${totalMin}分`;
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return `残り目安 ${h}時間${m > 0 ? `${m}分` : ""}`;
}

function formatDuration(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
    : `${m}:${String(sec).padStart(2, "0")}`;
}

const FAILURE_MESSAGES: Record<string, string> = {
  input_invalid: "動画を読み込めませんでした。別の動画でお試しください。",
  analyze_error: "解析中にエラーが発生しました。",
  edit_error: "編集中にエラーが発生しました。",
  retry_exhausted: "解析に繰り返し失敗しました。動画を確認してもう一度お試しください。",
};

export default function MatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  const { data: match, mutate } = useSWR(["match", id], () => api.getMatch(id), {
    refreshInterval: (data) => (data && ["done", "failed"].includes(data.status) ? 0 : 4000),
  });

  const isDone = match?.status === "done";

  const { data: segments } = useSWR(isDone ? ["segments", id] : null, () => api.getSegments(id));
  const { data: playback } = useSWR(isDone ? ["playback", id] : null, () => api.getPlayback(id));

  const editedAsset = match?.assets.find((a) => a.kind === "edited");
  const normalizedAsset = match?.assets.find((a) => a.kind === "normalized");

  const handleShare = async () => {
    const res = await api.createShare(id);
    setShareUrl(res.url);
    if (navigator.share) {
      navigator.share({ url: res.url, title: match?.title }).catch(() => {});
    } else {
      navigator.clipboard?.writeText(location.origin + res.url);
    }
  };

  if (!match) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <header style={{ padding: "14px 16px 6px", display: "flex", alignItems: "center", gap: 8 }}>
        <button
          onClick={() => router.push("/")}
          style={{
            width: 26,
            height: 26,
            borderRadius: "50%",
            background: "var(--surface)",
            border: "1px solid var(--line-hair)",
          }}
          aria-label="戻る"
        >
          ←
        </button>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{match.title}</div>
      </header>

      {match.status === "failed" && (
        <div style={{ padding: 16 }}>
          <div
            style={{
              background: "var(--sand-soft)",
              borderRadius: 12,
              padding: 14,
              fontSize: 13,
              lineHeight: 1.6,
            }}
          >
            {FAILURE_MESSAGES[match.failure_reason?.code || ""] || "解析できませんでした。"}
          </div>
        </div>
      )}

      {!isDone && match.status !== "failed" && (
        <>
          <div
            style={{
              margin: "8px 16px",
              aspectRatio: "16/10",
              borderRadius: 12,
              background: "linear-gradient(135deg,#1a2b22,#10221a)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div style={{ color: "var(--ball)", fontSize: 12, fontWeight: 700 }}>
              {STATUS_LABEL_JA[match.status]}
            </div>
          </div>

          <div style={{ margin: "0 16px", padding: "0 16px" }}>
            <div style={{ height: 6, background: "var(--sand-soft)", borderRadius: 3, overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  width: `${match.progress.pct}%`,
                  background: "var(--court)",
                  borderRadius: 3,
                  transition: "width 0.5s ease",
                }}
              />
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 11,
                color: "var(--ink-secondary)",
                marginTop: 4,
              }}
            >
              <span>{match.progress.pct}%</span>
              {(() => {
                const remaining = estimateRemainingMs(match.created_at, match.progress.pct);
                return remaining != null ? <span>{formatRemaining(remaining)}</span> : null;
              })()}
            </div>
          </div>

          {match.preflight_report?.degraded && (
            <div
              style={{
                margin: "4px 16px 0",
                padding: "10px 12px",
                background: "var(--sand-soft)",
                borderRadius: 10,
                fontSize: 11,
                lineHeight: 1.5,
                display: "flex",
                gap: 8,
              }}
            >
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--sand)", marginTop: 4, flexShrink: 0 }} />
              <div>
                コートを見つけられなかったため、動きだけで区間を判定しています。
                精度が低い場合は区間を直してください。
              </div>
            </div>
          )}

          {!match.self_side && (
            <div style={{ margin: "10px 16px 0", padding: "12px", background: "var(--court-soft)", borderRadius: 10 }}>
              <p style={{ fontSize: 12, fontWeight: 700, margin: "0 0 8px" }}>
                あなたはどちら側でプレーしていますか？
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => api.setSelfSide(id, "near").then((m) => mutate(m, false))}
                  style={{ flex: 1, padding: 10, borderRadius: 8, border: "none", background: "var(--court)", color: "#fff", fontSize: 12, fontWeight: 700 }}
                >
                  手前（カメラ側）
                </button>
                <button
                  onClick={() => api.setSelfSide(id, "far").then((m) => mutate(m, false))}
                  style={{ flex: 1, padding: 10, borderRadius: 8, border: "1px solid var(--line-hair)", background: "var(--surface-raised)", color: "var(--ink)", fontSize: 12, fontWeight: 700 }}
                >
                  奥側
                </button>
              </div>
            </div>
          )}

          <p style={{ textAlign: "center", fontSize: 11, color: "var(--ink-secondary)", padding: "8px 16px 0" }}>
            閉じてOK。終わったら通知でお知らせします
          </p>
        </>
      )}

      {isDone && playback && (
        <>
          <div style={{ margin: "8px 16px 4px", aspectRatio: "16/10" }}>
            <VideoPlayer playlistUrl={playback.playlist_url} thumbnailUrl={playback.thumbnail_url} />
          </div>

          {normalizedAsset?.duration_s != null && editedAsset?.duration_s != null && (
            <div style={{ padding: "10px 16px 4px" }}>
              <div style={{ fontSize: 11, color: "var(--ink-secondary)" }}>保存された時間</div>
              <div style={{ fontSize: 28, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                <span style={{ fontSize: 15, color: "var(--ink-secondary)", fontWeight: 500, marginRight: 6 }}>
                  {formatDuration(normalizedAsset.duration_s)} →
                </span>
                {formatDuration(editedAsset.duration_s)}
              </div>
            </div>
          )}

          {segments && normalizedAsset?.duration_s != null && (
            <div style={{ padding: "10px 16px" }}>
              <div style={{ fontSize: 10, color: "var(--ink-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                プレー区間
              </div>
              <Ribbon durationS={normalizedAsset.duration_s} segments={segments.effective} />
            </div>
          )}

          <ScorePad matchId={id} />

          <FeedbackPanel matchId={id} />

          <StatsPanel matchId={id} />

          <div style={{ display: "flex", gap: 8, padding: "12px 16px" }}>
            <button
              onClick={handleShare}
              style={{
                flex: 1,
                fontSize: 12,
                fontWeight: 700,
                padding: 10,
                borderRadius: 10,
                border: "1px solid var(--line-hair)",
                background: "var(--surface-raised)",
                color: "var(--ink)",
              }}
            >
              共有する
            </button>
            <button
              onClick={() => router.push(`/matches/${id}/edit`)}
              style={{
                flex: 1,
                fontSize: 12,
                fontWeight: 700,
                padding: 10,
                borderRadius: 10,
                border: "none",
                background: "var(--court)",
                color: "#fff",
              }}
            >
              区間を直す
            </button>
          </div>

          {shareUrl && (
            <p style={{ textAlign: "center", fontSize: 11, color: "var(--ink-secondary)" }}>
              共有リンク: {location.origin}
              {shareUrl}
            </p>
          )}
        </>
      )}
    </div>
  );
}
