import type { MatchStatus } from "@/lib/api";

export function StatusChip({ status }: { status: MatchStatus }) {
  const done = status === "done";
  const failed = status === "failed";
  return (
    <span
      style={{
        fontSize: 10,
        padding: "2px 7px",
        borderRadius: 999,
        fontWeight: 600,
        whiteSpace: "nowrap",
        background: failed ? "#f6dcd6" : done ? "var(--court-soft)" : "var(--sand-soft)",
        color: failed ? "var(--alert)" : done ? "var(--court)" : "var(--sand)",
      }}
    >
      {failed ? "失敗" : done ? "完了" : "解析中"}
    </span>
  );
}
