"use client";

/**
 * 区間修正画面（11-ui-design.md §4）。
 * ドラッグ操作は本実装では数値ステップ操作（±0.5秒ボタン）に簡略化している
 * （ブラウザでの実機テストなしにドラッグジェスチャーの正確な実装は検証できないため。
 * op（add/remove/adjust）モデル自体は設計どおり。将来UIをドラッグに差し替える際も
 * バックエンドAPIの変更は不要）。
 */

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";

interface PendingOp {
  op: "add" | "remove" | "adjust";
  base_segment_id?: string;
  start_s?: number;
  end_s?: number;
  label: string;
}

export default function SegmentEditorPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const { data: match } = useSWR(["match", id], () => api.getMatch(id));
  const { data: segments, mutate } = useSWR(["segments", id], () => api.getSegments(id));

  const [pendingOps, setPendingOps] = useState<PendingOp[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const normalizedAsset = match?.assets.find((a) => a.kind === "normalized");
  const durationS = normalizedAsset?.duration_s ?? 0;

  // rawのeffective idを取れるよう、effective区間に対応するsegment idを推定する
  // （簡易実装：raw行のうちaliveなadd行をstart_sで対応付ける）
  const effectiveWithIds = (segments?.raw ?? [])
    .filter((r) => r.op === "add")
    .map((r) => ({ id: r.id, start_s: r.start_s!, end_s: r.end_s! }));

  const adjustStep = (id: string, field: "start_s" | "end_s", delta: number) => {
    const seg = effectiveWithIds.find((s) => s.id === id);
    if (!seg) return;
    const newStart = field === "start_s" ? seg.start_s + delta : seg.start_s;
    const newEnd = field === "end_s" ? seg.end_s + delta : seg.end_s;
    if (newStart >= newEnd || newStart < 0 || newEnd > durationS) return;

    setPendingOps((prev) => [
      ...prev.filter((p) => p.base_segment_id !== id),
      {
        op: "adjust",
        base_segment_id: id,
        start_s: newStart,
        end_s: newEnd,
        label: `区間を調整（${newStart.toFixed(1)}s〜${newEnd.toFixed(1)}s）`,
      },
    ]);
  };

  const removeSegment = (id: string) => {
    setPendingOps((prev) => [
      ...prev.filter((p) => p.base_segment_id !== id),
      { op: "remove", base_segment_id: id, label: "区間を削除" },
    ]);
  };

  const undoLast = () => setPendingOps((prev) => prev.slice(0, -1));

  const previewSegments = (() => {
    const map = new Map(effectiveWithIds.map((s) => [s.id, { ...s, alive: true }]));
    for (const op of pendingOps) {
      if (!op.base_segment_id) continue;
      const entry = map.get(op.base_segment_id);
      if (!entry) continue;
      if (op.op === "remove") entry.alive = false;
      if (op.op === "adjust") {
        entry.start_s = op.start_s!;
        entry.end_s = op.end_s!;
      }
    }
    return Array.from(map.values()).filter((e) => e.alive);
  })();

  const submit = async () => {
    if (!segments || pendingOps.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.patchSegments(
        id,
        segments.revision,
        pendingOps.map(({ label, ...op }) => op)
      );
      await api.recut(id);
      router.push(`/matches/${id}`);
    } catch (e: any) {
      setError(e.message || "更新に失敗しました");
    } finally {
      setSubmitting(false);
    }
  };

  if (!match || !segments) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <header style={{ padding: "14px 16px 6px", display: "flex", alignItems: "center", gap: 8 }}>
        <button
          onClick={() => router.back()}
          style={{ width: 26, height: 26, borderRadius: "50%", background: "var(--surface)", border: "1px solid var(--line-hair)" }}
        >
          ←
        </button>
        <div style={{ fontSize: 14, fontWeight: 700 }}>区間を直す</div>
      </header>

      <div style={{ margin: "20px 16px 8px" }}>
        <Ribbon durationS={durationS} segments={previewSegments} height={44} />
        <p style={{ fontSize: 11, color: "var(--ink-secondary)", textAlign: "center", marginTop: 8 }}>
          各区間を±0.5秒で調整、または削除できます
        </p>
      </div>

      <div style={{ padding: "0 16px", display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
        {effectiveWithIds.map((seg) => {
          const removed = pendingOps.some((p) => p.base_segment_id === seg.id && p.op === "remove");
          if (removed) return null;
          return (
            <div
              key={seg.id}
              style={{
                border: "1px solid var(--line-hair)",
                borderRadius: 10,
                padding: 10,
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 12,
              }}
            >
              <span style={{ flex: 1 }}>
                {seg.start_s.toFixed(1)}s 〜 {seg.end_s.toFixed(1)}s
              </span>
              <button onClick={() => adjustStep(seg.id, "start_s", -0.5)}>◀開始</button>
              <button onClick={() => adjustStep(seg.id, "start_s", 0.5)}>開始▶</button>
              <button onClick={() => adjustStep(seg.id, "end_s", -0.5)}>◀終了</button>
              <button onClick={() => adjustStep(seg.id, "end_s", 0.5)}>終了▶</button>
              <button onClick={() => removeSegment(seg.id)} style={{ color: "var(--alert)" }}>
                削除
              </button>
            </div>
          );
        })}
      </div>

      <div style={{ display: "flex", justifyContent: "center", gap: 16, margin: "14px 0 6px", fontSize: 11, color: "var(--ink-secondary)" }}>
        <button onClick={undoLast} disabled={pendingOps.length === 0} style={{ background: "none", border: "none" }}>
          ↺ 取り消し（{pendingOps.length}件の変更）
        </button>
      </div>

      {error && <p style={{ textAlign: "center", fontSize: 12, color: "var(--alert)" }}>{error}</p>}

      <div style={{ padding: "12px 16px 24px" }}>
        <button
          onClick={submit}
          disabled={submitting || pendingOps.length === 0}
          style={{
            width: "100%",
            padding: 12,
            borderRadius: 10,
            border: "none",
            background: "var(--court)",
            color: "#fff",
            fontWeight: 700,
            fontSize: 13,
            opacity: pendingOps.length === 0 ? 0.5 : 1,
          }}
        >
          {submitting ? "作り直しています…" : "この内容で作り直す"}
        </button>
      </div>
    </div>
  );
}
