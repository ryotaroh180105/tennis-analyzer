"use client";

import { useEffect, useRef } from "react";

interface VideoPlayerProps {
  playlistUrl: string;
  thumbnailUrl?: string | null;
  onTimeUpdate?: (t: number) => void;
  videoRef?: React.MutableRefObject<HTMLVideoElement | null>;
}

export function VideoPlayer({ playlistUrl, thumbnailUrl, onTimeUpdate, videoRef: externalRef }: VideoPlayerProps) {
  const internalRef = useRef<HTMLVideoElement | null>(null);
  const videoRef = externalRef || internalRef;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls: any;
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = playlistUrl; // Safari/iOSはネイティブHLS対応
    } else {
      import("hls.js").then(({ default: Hls }) => {
        if (Hls.isSupported()) {
          hls = new Hls();
          hls.loadSource(playlistUrl);
          hls.attachMedia(video);
        }
      });
    }

    return () => {
      hls?.destroy();
    };
  }, [playlistUrl, videoRef]);

  return (
    <video
      ref={videoRef}
      controls
      playsInline
      poster={thumbnailUrl ?? undefined}
      onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
      style={{ width: "100%", height: "100%", borderRadius: 12, background: "#10221a", display: "block" }}
    />
  );
}
