"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";

export function ScorePad({ matchId }: { matchId: string }) {
  const { data: score, mutate } = useSWR(["score", matchId], () => api.getScore(matchId));
  const [pending, setPending] = useState(false);

  if (!score) return null;

  const tap = async (winner: "self" | "opponent") => {
    if (pending || score.match_winner) return;
    setPending(true);
    try {
      const next = await api.addScorePoint(matchId, winner);
      mutate(next, false);
    } finally {
      setPending(false);
    }
  };

  const undo = async () => {
    if (pending || score.total_points === 0) return;
    setPending(true);
    try {
      const next = await api.undoScorePoint(matchId);
      mutate(next, false);
    } finally {
      setPending(false);
    }
  };

  const gameLabel = score.tiebreak
    ? { self: String(score.tiebreak.self), opponent: String(score.tiebreak.opponent) }
    : score.current_game_display ?? { self: "0", opponent: "0" };

  return (
    <div style={{ padding: "10px 16px" }}>
      <div style={{ fontSize: 10, color: "var(--ink-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
        スコア（手入力）
      </div>

      {score.match_winner && (
        <p style={{ fontSize: 13, fontWeight: 700, margin: "0 0 8px", color: "var(--court)" }}>
          {score.match_winner === "self" ? "勝利しました" : "敗北しました"}
        </p>
      )}

      <div style={{ display: "flex", gap: 12, marginBottom: 10, fontSize: 12, color: "var(--ink-secondary)" }}>
        {score.completed_sets.map((s, i) => (
          <span key={i}>
            {s.self}-{s.opponent}
          </span>
        ))}
        <span>
          （現在セット {score.current_set_games.self}-{score.current_set_games.opponent}）
        </span>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => tap("self")}
          disabled={pending || !!score.match_winner}
          style={{
            flex: 1,
            padding: "16px 8px",
            borderRadius: 12,
            border: "none",
            background: "var(--court)",
            color: "#fff",
          }}
        >
          <div style={{ fontSize: 11, opacity: 0.85 }}>自分</div>
          <div style={{ fontSize: 22, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{gameLabel.self}</div>
        </button>
        <button
          onClick={() => tap("opponent")}
          disabled={pending || !!score.match_winner}
          style={{
            flex: 1,
            padding: "16px 8px",
            borderRadius: 12,
            border: "1px solid var(--line-hair)",
            background: "var(--surface-raised)",
            color: "var(--ink)",
          }}
        >
          <div style={{ fontSize: 11, opacity: 0.7 }}>相手</div>
          <div style={{ fontSize: 22, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{gameLabel.opponent}</div>
        </button>
      </div>

      <button
        onClick={undo}
        disabled={pending || score.total_points === 0}
        style={{
          marginTop: 8,
          width: "100%",
          padding: 8,
          borderRadius: 8,
          border: "none",
          background: "none",
          color: "var(--ink-secondary)",
          fontSize: 12,
        }}
      >
        1つ前に戻す
      </button>
    </div>
  );
}
