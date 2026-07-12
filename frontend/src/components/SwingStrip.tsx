"use client";

/**
 * スイング一覧ストリップ（12-form-analysis.md §11補追、設計レビュー13 E'）。
 * フォーム解析の集約値だけでなく、個々のスイングの有効/無効・外れ値を可視化し、
 * タップでそのスイングの実測値を確認できるようにする。
 */

import { useState } from "react";
import { FORM_METRIC_LABEL_JA, type FormMetric, type Swing } from "@/lib/api";

interface SwingStripProps {
  swings: Swing[];
  metrics: FormMetric[];
}

type SwingQuality = "ok" | "low_completeness" | "outlier";

function classifySwing(swing: Swing, metrics: FormMetric[]): SwingQuality {
  const values = Object.values(swing.metrics);
  const withValue = values.filter((v) => v.value != null).length;
  const completeness = values.length > 0 ? withValue / values.length : 0;
  if (completeness < 0.5) return "low_completeness";

  const hasOutlier = metrics.some((m) => {
    const swingValue = swing.metrics[m.id]?.value;
    if (swingValue == null || m.measured == null || m.iqr == null || m.iqr <= 0) return false;
    return Math.abs(swingValue - m.measured) > m.iqr * 1.5;
  });
  if (hasOutlier) return "outlier";

  return "ok";
}

const QUALITY_COLOR: Record<SwingQuality, string> = {
  ok: "var(--court)",
  low_completeness: "var(--ink-secondary)",
  outlier: "var(--sand)",
};

const QUALITY_LABEL_JA: Record<SwingQuality, string> = {
  ok: "有効なスイング",
  low_completeness: "映り込み不足で一部の指標が測定できていません",
  outlier: "他のスイングと比べて値が大きく外れています",
};

function formatSwingValue(v: number | null, unit: string): string {
  if (v == null) return "—";
  const suffix = unit === "deg" ? "°" : unit === "ms" ? "ms" : "";
  return `${v}${suffix}`;
}

export function SwingStrip({ swings, metrics }: SwingStripProps) {
  const [selected, setSelected] = useState<number | null>(null);

  if (swings.length === 0) return null;

  const metricById = new Map(metrics.map((m) => [m.id, m]));
  const selectedSwing = selected != null ? swings[selected] : null;

  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          fontSize: 10,
          color: "var(--ink-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          marginBottom: 6,
        }}
      >
        スイング一覧（{swings.length}本）
      </div>
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 4 }}>
        {swings.map((swing, i) => {
          const quality = classifySwing(swing, metrics);
          const isSelected = selected === i;
          return (
            <button
              key={i}
              onClick={() => setSelected(isSelected ? null : i)}
              aria-label={`スイング${i + 1}: ${QUALITY_LABEL_JA[quality]}`}
              style={{
                flexShrink: 0,
                width: 32,
                height: 32,
                borderRadius: "50%",
                border: isSelected ? "2px solid var(--ink)" : "1px solid var(--line-hair)",
                background: quality === "ok" ? "var(--court-soft)" : "var(--surface-raised)",
                color: QUALITY_COLOR[quality],
                fontSize: 11,
                fontWeight: 700,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {i + 1}
            </button>
          );
        })}
      </div>

      {selectedSwing && (
        <div
          style={{
            marginTop: 8,
            padding: 12,
            borderRadius: 10,
            background: "var(--surface-raised)",
            border: "1px solid var(--line-hair)",
            fontSize: 11,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>
            スイング{selected! + 1}（{selectedSwing.t.toFixed(1)}秒）
          </div>
          <div style={{ color: "var(--ink-secondary)", marginBottom: 8 }}>
            {QUALITY_LABEL_JA[classifySwing(selectedSwing, metrics)]}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {Object.values(selectedSwing.metrics).map((sv) => {
              const m = metricById.get(sv.id);
              return (
                <div key={sv.id} style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{FORM_METRIC_LABEL_JA[sv.id] || sv.id}</span>
                  <span style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                    {formatSwingValue(sv.value, m?.unit || "")}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
