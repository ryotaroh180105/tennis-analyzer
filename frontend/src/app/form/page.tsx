"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import {
  api,
  FORM_SHOT_TYPE_LABEL_JA,
  FORM_STATUS_LABEL_JA,
  type BackhandStyle,
  type FormShotType,
} from "@/lib/api";
import { UploadSheet } from "@/components/UploadSheet";

const SHOT_TYPES: FormShotType[] = ["serve", "forehand", "backhand", "smash", "volley"];

export default function FormListPage() {
  const router = useRouter();
  const { data: sessions, mutate } = useSWR("form-sessions", api.listFormSessions, {
    refreshInterval: 5000,
  });
  const [showUpload, setShowUpload] = useState(false);
  const [shotType, setShotType] = useState<FormShotType>("forehand");
  const [backhandStyle, setBackhandStyle] = useState<BackhandStyle>("auto");

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
        <div style={{ fontSize: 17, fontWeight: 700 }}>フォーム解析</div>
      </header>

      <p style={{ padding: "0 16px 8px", fontSize: 12, color: "var(--ink-secondary)", lineHeight: 1.6 }}>
        近距離・単独で撮った練習動画をアップロードすると、フォームを骨格解析して
        参考レンジと比較します（試験運用中の機能です）。
      </p>

      <div style={{ padding: "0 16px 12px" }}>
        <div style={{ fontSize: 10, color: "var(--ink-secondary)", marginBottom: 6 }}>次にアップロードするショット</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {SHOT_TYPES.map((st) => (
            <button
              key={st}
              onClick={() => setShotType(st)}
              style={{
                padding: "6px 12px",
                borderRadius: 999,
                border: st === shotType ? "none" : "1px solid var(--line-hair)",
                background: st === shotType ? "var(--sand)" : "var(--surface-raised)",
                color: st === shotType ? "#fff" : "var(--ink)",
                fontSize: 12,
                fontWeight: 700,
              }}
            >
              {FORM_SHOT_TYPE_LABEL_JA[st]}
            </button>
          ))}
        </div>

        {shotType === "backhand" && (
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            {(["auto", "one_handed", "two_handed"] as BackhandStyle[]).map((style) => (
              <button
                key={style}
                onClick={() => setBackhandStyle(style)}
                style={{
                  padding: "5px 10px",
                  borderRadius: 999,
                  border: style === backhandStyle ? "none" : "1px solid var(--line-hair)",
                  background: style === backhandStyle ? "var(--court)" : "var(--surface-raised)",
                  color: style === backhandStyle ? "#fff" : "var(--ink-secondary)",
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                {style === "auto" ? "自動判定" : style === "one_handed" ? "片手" : "両手"}
              </button>
            ))}
          </div>
        )}
      </div>

      <main style={{ flex: 1, overflowY: "auto", padding: "4px 16px 100px", display: "flex", flexDirection: "column", gap: 10 }}>
        {sessions?.length === 0 && (
          <div style={{ padding: "40px 8px", textAlign: "center", color: "var(--ink-secondary)", fontSize: 13, lineHeight: 1.7 }}>
            練習動画を1本アップロードしてみてください。
          </div>
        )}

        {sessions?.map((s) => (
          <div
            key={s.id}
            onClick={() => router.push(`/form/${s.id}`)}
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
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 10,
                fontWeight: 700,
                color: "#fff",
                background: "linear-gradient(135deg, var(--sand), var(--sand-soft))",
              }}
            >
              {FORM_SHOT_TYPE_LABEL_JA[s.shot_type]}
            </div>
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
              {FORM_STATUS_LABEL_JA[s.status]}
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
          ＋ {FORM_SHOT_TYPE_LABEL_JA[shotType]}動画を追加
        </button>
      </div>

      {showUpload && (
        <UploadSheet
          onClose={() => setShowUpload(false)}
          createFn={(uploadId, title) =>
            api.createFormSession(uploadId, title, shotType, shotType === "backhand" ? backhandStyle : undefined)
          }
          title={`${FORM_SHOT_TYPE_LABEL_JA[shotType]}動画を追加`}
          description="全身が映る近距離・単独のアングルでアップロードしてください"
          onCreated={(id) => {
            setShowUpload(false);
            mutate();
            router.push(`/form/${id}`);
          }}
        />
      )}
    </div>
  );
}
