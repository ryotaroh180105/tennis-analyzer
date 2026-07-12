"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { api, LOW_CONFIDENCE_THRESHOLD } from "@/lib/api";
import { Ribbon } from "@/components/Ribbon";
import { VideoPlayer } from "@/components/VideoPlayer";

export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const { data: playback, error } = useSWR(["share-playback", token], () => api.getSharePlayback(token));

  // 読み取り専用リボン（11 §5「プレーヤー＋リボン（読み取り専用）」）。共有ページが
  // 再生するのは編集済み（デッドタイム除去済み）動画のため、元のstart_s/end_sではなく
  // 「区間の長さの累積」＝編集済み動画上のおおよその章区切りとして再解釈する
  // （FFmpegのキーフレームスナップにより数秒のズレはあり得る、あくまで目安）。
  let ribbonDurationS = 0;
  const ribbonChapters =
    playback?.segments?.map((s) => {
      const start = ribbonDurationS;
      ribbonDurationS += s.end_s - s.start_s;
      return { start_s: start, end_s: ribbonDurationS, lowConfidence: s.confidence != null && s.confidence < LOW_CONFIDENCE_THRESHOLD };
    }) ?? [];

  return (
    <div style={{ padding: 14 }}>
      <div style={{ background: "var(--surface-raised)", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ aspectRatio: "16/9" }}>
          {error && (
            <div style={{ padding: 20, textAlign: "center", fontSize: 13, color: "var(--ink-secondary)" }}>
              この動画は見つかりませんでした（削除されたか、リンクが無効です）
            </div>
          )}
          {playback && <VideoPlayer playlistUrl={playback.playlist_url} thumbnailUrl={playback.thumbnail_url} />}
        </div>

        {ribbonChapters.length > 0 && (
          <div style={{ padding: "10px 16px 0" }}>
            <Ribbon durationS={ribbonDurationS} segments={ribbonChapters} height={14} />
          </div>
        )}

        <div style={{ padding: 16 }}>
          <div
            style={{
              background: "var(--court)",
              color: "#fff",
              borderRadius: 12,
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 700 }}>自分の試合も、撮って送るだけ</div>
            <div style={{ fontSize: 11, opacity: 0.9 }}>スマホ1台で編集・ハイライトまで自動生成</div>
            <a
              href="/"
              style={{
                background: "#fff",
                color: "var(--court)",
                fontWeight: 700,
                fontSize: 12,
                padding: 9,
                borderRadius: 8,
                textAlign: "center",
                textDecoration: "none",
              }}
            >
              はじめる
            </a>
          </div>

          <p style={{ fontSize: 10, color: "var(--ink-secondary)", textAlign: "center", marginTop: 14 }}>
            この動画の削除を依頼する
          </p>
        </div>
      </div>
    </div>
  );
}
