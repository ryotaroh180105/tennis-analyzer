"use client";

/**
 * シグネチャ要素：区間タイムライン・リボン（11-ui-design.md）。
 * コート（緑）とデッドタイム（砂）というテニスコートの実風景を時間軸に転写する。
 */

import { useMemo } from "react";

export interface RibbonSegment {
  start_s: number;
  end_s: number;
  lowConfidence?: boolean;
}

interface RibbonProps {
  durationS: number;
  segments: RibbonSegment[];
  currentTimeS?: number;
  height?: number;
  onSeek?: (t: number) => void;
}

export function Ribbon({ durationS, segments, currentTimeS, height = 22, onSeek }: RibbonProps) {
  const blocks = useMemo(() => {
    if (durationS <= 0) return [];
    const sorted = [...segments].sort((a, b) => a.start_s - b.start_s);
    const out: Array<{ kind: "court" | "dead" | "low"; widthPct: number }> = [];
    let cursor = 0;
    for (const seg of sorted) {
      if (seg.start_s > cursor) {
        out.push({ kind: "dead", widthPct: ((seg.start_s - cursor) / durationS) * 100 });
      }
      out.push({
        kind: seg.lowConfidence ? "low" : "court",
        widthPct: ((seg.end_s - seg.start_s) / durationS) * 100,
      });
      cursor = seg.end_s;
    }
    if (cursor < durationS) {
      out.push({ kind: "dead", widthPct: ((durationS - cursor) / durationS) * 100 });
    }
    return out;
  }, [segments, durationS]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSeek || durationS <= 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    onSeek(ratio * durationS);
  };

  const playheadPct = currentTimeS != null && durationS > 0 ? (currentTimeS / durationS) * 100 : null;

  return (
    <div
      onClick={handleClick}
      style={{
        display: "flex",
        height,
        borderRadius: 6,
        overflow: "hidden",
        position: "relative",
        cursor: onSeek ? "pointer" : "default",
      }}
      role="slider"
      aria-label="区間タイムライン"
      aria-valuemin={0}
      aria-valuemax={durationS}
      aria-valuenow={currentTimeS ?? 0}
    >
      {blocks.map((b, i) => (
        <div
          key={i}
          style={{
            width: `${b.widthPct}%`,
            background:
              b.kind === "court" ? "var(--court)" : b.kind === "low" ? "var(--court)" : "var(--sand)",
            opacity: b.kind === "dead" ? 0.55 : b.kind === "low" ? 0.45 : 1,
            backgroundImage:
              b.kind === "low"
                ? "repeating-linear-gradient(135deg, transparent, transparent 3px, rgba(255,255,255,0.35) 3px, rgba(255,255,255,0.35) 5px)"
                : undefined,
          }}
        />
      ))}
      {playheadPct !== null && (
        <div
          style={{
            position: "absolute",
            top: -3,
            left: `${playheadPct}%`,
            width: 10,
            height: height + 6,
            background: "var(--ball)",
            borderRadius: 3,
            boxShadow: "0 0 0 2px var(--surface-raised)",
            transform: "translateX(-50%)",
          }}
        />
      )}
    </div>
  );
}
