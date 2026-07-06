"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { StatusChip } from "@/components/StatusChip";
import { UploadSheet } from "@/components/UploadSheet";

export default function HomePage() {
  const router = useRouter();
  const { data: matches, mutate } = useSWR("matches", api.listMatches, {
    refreshInterval: 5000, // ポーリング（10 §API契約。WebSocketは入れない）
  });
  const [showUpload, setShowUpload] = useState(false);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <header
        style={{
          padding: "14px 16px 10px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <div style={{ fontSize: 17, fontWeight: 700 }}>試合</div>
      </header>

      <main style={{ flex: 1, overflowY: "auto", padding: "4px 16px 100px", display: "flex", flexDirection: "column", gap: 10 }}>
        {matches?.length === 0 && (
          <div style={{ padding: "40px 8px", textAlign: "center", color: "var(--ink-secondary)", fontSize: 13, lineHeight: 1.7 }}>
            過去に撮った試合動画を1本、そのまま入れてみてください。
            <br />
            画角が悪くても大丈夫 — まず編集して返します。
          </div>
        )}

        {matches?.map((m) => (
          <div
            key={m.id}
            onClick={() => router.push(`/matches/${m.id}`)}
            style={{
              background: "var(--surface)",
              border: "1px solid var(--line-hair)",
              borderRadius: 12,
              padding: 10,
              display: "flex",
              gap: 10,
              alignItems: "center",
              cursor: "pointer",
            }}
          >
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: 8,
                flexShrink: 0,
                background: "linear-gradient(135deg, var(--court), var(--court-soft))",
              }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: 13, fontWeight: 600, margin: "0 0 2px" }}>{m.title}</p>
              <p style={{ fontSize: 11, color: "var(--ink-secondary)", margin: 0 }}>
                {new Date(m.created_at).toLocaleDateString("ja-JP")}
              </p>
            </div>
            <StatusChip status={m.status} />
          </div>
        ))}
      </main>

      <div
        style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          maxWidth: 480,
          margin: "0 auto",
          padding: "12px 16px 24px",
          background: "linear-gradient(to top, var(--surface) 60%, transparent)",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <button
          onClick={() => setShowUpload(true)}
          style={{
            background: "var(--court)",
            color: "#fff",
            border: "none",
            borderRadius: 999,
            padding: "13px 26px",
            fontSize: 14,
            fontWeight: 700,
            boxShadow: "0 4px 12px rgba(46,125,91,0.35)",
          }}
        >
          ＋ 動画を追加
        </button>
      </div>

      {showUpload && (
        <UploadSheet
          onClose={() => setShowUpload(false)}
          onCreated={(matchId) => {
            setShowUpload(false);
            mutate();
            router.push(`/matches/${matchId}`);
          }}
        />
      )}
    </div>
  );
}
