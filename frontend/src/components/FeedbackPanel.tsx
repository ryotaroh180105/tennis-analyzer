"use client";

import useSWR from "swr";
import { api } from "@/lib/api";

export function FeedbackPanel({ matchId }: { matchId: string }) {
  const { data: feedback } = useSWR(
    ["feedback", matchId],
    () => api.getFeedback(matchId).catch(() => null),
    { refreshInterval: (data) => (data ? 0 : 5000) }
  );

  if (!feedback) return null;

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
        今回のフィードバック
      </div>

      <div
        style={{
          background: "var(--court-soft)",
          borderRadius: 12,
          padding: 14,
        }}
      >
        <p style={{ fontSize: 13, lineHeight: 1.6, margin: "0 0 10px", fontWeight: 700 }}>
          {feedback.summary}
        </p>

        {feedback.tendencies.length > 0 && (
          <div style={{ marginBottom: feedback.drill_suggestions.length > 0 ? 10 : 0 }}>
            {feedback.tendencies.map((t, i) => (
              <div key={i} style={{ display: "flex", gap: 6, fontSize: 12, lineHeight: 1.6, marginBottom: 4 }}>
                <span style={{ color: "var(--sand)" }}>・</span>
                <span>{t}</span>
              </div>
            ))}
          </div>
        )}

        {feedback.drill_suggestions.length > 0 && (
          <div>
            <div style={{ fontSize: 10, color: "var(--ink-secondary)", fontWeight: 700, marginBottom: 4 }}>
              次の練習
            </div>
            {feedback.drill_suggestions.map((d, i) => (
              <div key={i} style={{ display: "flex", gap: 6, fontSize: 12, lineHeight: 1.6, marginBottom: 4 }}>
                <span style={{ color: "var(--court)" }}>✓</span>
                <span>{d}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
