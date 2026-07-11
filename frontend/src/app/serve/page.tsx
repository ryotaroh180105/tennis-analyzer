"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { api, SERVE_STATUS_LABEL_JA } from "@/lib/api";
import { UploadSheet } from "@/components/UploadSheet";

export default function ServeListPage() {
  const router = useRouter();
  const { data: sessions, mutate } = useSWR("serve-sessions", api.listServeSessions, {
    refreshInterval: 5000,
  });
  const [showUpload, setShowUpload] = useState(false);

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
        <div style={{ fontSize: 17, fontWeight: 700 }}>サーブ解析</div>
      </header>

      <p style={{ padding: "0 16px 12px", fontSize: 12, color: "var(--ink-secondary)", lineHeight: 1.6 }}>
        斜め後方・近距離から撮ったサーブ動画をアップロードすると、フォームを骨格解析して
        参考レンジと比較します（試験運用中の機能です）。
      </p>

      <main style={{ flex: 1, overflowY: "auto", padding: "4px 16px 100px", display: "flex", flexDirection: "column", gap: 10 }}>
        {sessions?.length === 0 && (
          <div style={{ padding: "40px 8px", textAlign: "center", color: "var(--ink-secondary)", fontSize: 13, lineHeight: 1.7 }}>
            サーブ練習動画を1本アップロードしてみてください。
          </div>
        )}

        {sessions?.map((s) => (
          <div
            key={s.id}
            onClick={() => router.push(`/serve/${s.id}`)}
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
                background: "linear-gradient(135deg, var(--sand), var(--sand-soft))",
              }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: 13, fontWeight: 600, margin: "0 0 2px" }}>{s.title}</p>
              <p style={{ fontSize: 11, color: "var(--ink-secondary)", margin: 0 }}>
                {new Date(s.created_at).toLocaleDateString("ja-JP")}
              </p>
            </div>
            <span
              style={{
                fontSize: 10,
                padding: "2px 7px",
                borderRadius: 999,
                fontWeight: 600,
                whiteSpace: "nowrap",
                background: s.status === "failed" ? "#f6dcd6" : s.status === "done" ? "var(--court-soft)" : "var(--sand-soft)",
                color: s.status === "failed" ? "var(--alert)" : s.status === "done" ? "var(--court)" : "var(--sand)",
              }}
            >
              {SERVE_STATUS_LABEL_JA[s.status]}
            </span>
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
            background: "var(--sand)",
            color: "#fff",
            border: "none",
            borderRadius: 999,
            padding: "13px 26px",
            fontSize: 14,
            fontWeight: 700,
            boxShadow: "0 4px 12px rgba(245,165,36,0.35)",
          }}
        >
          ＋ サーブ動画を追加
        </button>
      </div>

      {showUpload && (
        <UploadSheet
          onClose={() => setShowUpload(false)}
          createFn={api.createServeSession}
          title="サーブ動画を追加"
          description="斜め後方・近距離から撮った1本のサーブをアップロードしてください"
          onCreated={(id) => {
            setShowUpload(false);
            mutate();
            router.push(`/serve/${id}`);
          }}
        />
      )}
    </div>
  );
}
