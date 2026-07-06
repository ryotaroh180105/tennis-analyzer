"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import { VideoPlayer } from "@/components/VideoPlayer";

export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const { data: playback, error } = useSWR(["share-playback", token], () => api.getSharePlayback(token));

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
