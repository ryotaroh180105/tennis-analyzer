"use client";

import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import {
  api,
  FORM_METRIC_LABEL_JA,
  FORM_METRIC_STATUS_LABEL_JA,
  FORM_PHASE_LABEL_JA,
  FORM_SHOT_TYPE_LABEL_JA,
  FORM_STATUS_LABEL_JA,
  type FormMetric,
} from "@/lib/api";

const STATUS_COLOR: Record<FormMetric["status"], string> = {
  in_range: "var(--court)",
  borderline: "var(--sand)",
  out_of_range: "var(--alert)",
  unknown: "var(--ink-secondary)",
};

function formatValue(m: FormMetric): string {
  if (m.measured == null) return "—";
  const unit = m.unit === "deg" ? "°" : m.unit === "ms" ? "ms" : "";
  return `${m.measured}${unit}`;
}

function formatRange(m: FormMetric): string {
  const unit = m.unit === "deg" ? "°" : m.unit === "ms" ? "ms" : "";
  return `参考: ${m.elite_range[0]}〜${m.elite_range[1]}${unit}`;
}

export default function FormDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const { data: session } = useSWR(["form-session", id], () => api.getFormSession(id), {
    refreshInterval: (data) => (data && ["done", "failed"].includes(data.status) ? 0 : 3000),
  });
  const isDone = session?.status === "done";
  const { data: analysis } = useSWR(isDone ? ["form-analysis", id] : null, () => api.getFormAnalysis(id));

  if (!session) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <header style={{ padding: "14px 16px 6px", display: "flex", alignItems: "center", gap: 8 }}>
        <button
          onClick={() => router.push("/form")}
          style={{ width: 26, height: 26, borderRadius: "50%", background: "var(--surface)", border: "1px solid var(--line-hair)" }}
          aria-label="戻る"
        >
          ←
        </button>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{session.title}</div>
        <span style={{ fontSize: 11, color: "var(--ink-secondary)" }}>{FORM_SHOT_TYPE_LABEL_JA[session.shot_type]}</span>
      </header>

      {session.status === "failed" && (
        <div style={{ padding: 16 }}>
          <div style={{ background: "var(--sand-soft)", borderRadius: 12, padding: 14, fontSize: 13, lineHeight: 1.6 }}>
            {session.failure_reason?.message || "解析できませんでした。"}
          </div>
        </div>
      )}

      {!isDone && session.status !== "failed" && (
        <div
          style={{
            margin: "24px 16px",
            padding: 20,
            borderRadius: 12,
            background: "var(--sand-soft)",
            textAlign: "center",
            fontSize: 13,
            fontWeight: 700,
            color: "var(--sand)",
          }}
        >
          {FORM_STATUS_LABEL_JA[session.status]}
        </div>
      )}

      {isDone && analysis && analysis.insufficient_data && (
        <div style={{ margin: "16px", padding: 16, borderRadius: 12, background: "var(--sand-soft)", fontSize: 13, lineHeight: 1.7 }}>
          有効なスイングが少なく、まだ傾向を掴みきれていません。
          <br />
          全身が映るアングルで、複数回のスイングを含む動画をもう一度お試しください。
        </div>
      )}

      {isDone && analysis && !analysis.insufficient_data && (
        <div style={{ padding: "8px 16px 40px" }}>
          <div
            style={{
              background: "var(--court-soft)",
              borderRadius: 10,
              padding: 12,
              fontSize: 11,
              lineHeight: 1.6,
              marginBottom: 14,
            }}
          >
            数値は文献ベースの参考レンジとの比較で、断定的な診断ではありません
            （有効スイング {analysis.swing_count}本、骨格検出率{" "}
            {Math.round(analysis.confidence.pose_detection_ratio * 100)}%）。
            {analysis.citation_status === "placeholder_pending_literature_review" &&
              " レンジ自体は現在検証中の参考値です。"}
          </div>

          {analysis.feedback_metrics.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 10, color: "var(--ink-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                注目ポイント
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {analysis.feedback_metrics.map((mid) => {
                  const m = analysis.metrics.find((x) => x.id === mid);
                  if (!m) return null;
                  return (
                    <div key={mid} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--surface-raised)", border: "1px solid var(--line-hair)", borderRadius: 10, padding: "8px 12px" }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 700 }}>{FORM_METRIC_LABEL_JA[mid] || mid}</div>
                        <div style={{ fontSize: 10, color: "var(--ink-secondary)" }}>{formatRange(m)}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 14, fontWeight: 800, color: STATUS_COLOR[m.status] }}>{formatValue(m)}</div>
                        <div style={{ fontSize: 10, color: STATUS_COLOR[m.status] }}>{FORM_METRIC_STATUS_LABEL_JA[m.status]}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div style={{ fontSize: 10, color: "var(--ink-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
            全指標
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {analysis.metrics.map((m) => (
              <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--line-hair)" }}>
                <span>
                  {FORM_METRIC_LABEL_JA[m.id] || m.id}
                  <span style={{ color: "var(--ink-secondary)", fontSize: 10, marginLeft: 6 }}>
                    ({FORM_PHASE_LABEL_JA[m.phase] || m.phase})
                  </span>
                  {m.high_variance && (
                    <span style={{ marginLeft: 6, fontSize: 9, color: "var(--sand)", fontWeight: 700 }}>
                      毎回変わっています
                    </span>
                  )}
                </span>
                <span style={{ fontWeight: 700, color: STATUS_COLOR[m.status], fontVariantNumeric: "tabular-nums" }}>
                  {formatValue(m)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
