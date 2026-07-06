"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { isOnWifi, uploadFile, type UploadProgress } from "@/lib/uploader";

interface UploadSheetProps {
  onClose: () => void;
  onCreated: (matchId: string) => void;
}

export function UploadSheet({ onClose, onCreated }: UploadSheetProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [waitingForWifi, setWaitingForWifi] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startUpload = async (f: File) => {
    setError(null);
    try {
      const uploadId = await uploadFile(f, setProgress);
      const match = await api.createMatch(uploadId, f.name.replace(/\.[^.]+$/, ""));
      onCreated(match.id);
    } catch (e: any) {
      setError(e.message || "送信できませんでした");
    }
  };

  const handleFile = (f: File) => {
    setFile(f);
    if (!isOnWifi()) {
      setWaitingForWifi(true);
      return;
    }
    startUpload(f);
  };

  const pct = progress ? Math.round((progress.uploadedBytes / progress.totalBytes) * 100) : 0;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.35)",
        display: "flex",
        alignItems: "flex-end",
        zIndex: 50,
      }}
      onClick={(e) => e.target === e.currentTarget && !progress && onClose()}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 480,
          margin: "0 auto",
          background: "var(--surface-raised)",
          borderRadius: "20px 20px 0 0",
          padding: "18px 18px 26px",
        }}
      >
        <div style={{ width: 36, height: 4, background: "var(--line-hair)", borderRadius: 2, margin: "0 auto 16px" }} />

        {!file && (
          <>
            <p style={{ fontSize: 15, fontWeight: 700, margin: "0 0 4px" }}>動画を追加</p>
            <p style={{ fontSize: 12, color: "var(--ink-secondary)", margin: "0 0 16px" }}>
              試合・練習動画をそのままアップロードしてください
            </p>
            <input
              ref={inputRef}
              type="file"
              accept="video/*"
              style={{ display: "none" }}
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
            <button
              onClick={() => inputRef.current?.click()}
              style={{
                width: "100%",
                padding: 14,
                borderRadius: 12,
                border: "none",
                background: "var(--court)",
                color: "#fff",
                fontWeight: 700,
                fontSize: 14,
              }}
            >
              動画を選ぶ
            </button>
          </>
        )}

        {file && (
          <>
            <p style={{ fontSize: 15, fontWeight: 700, margin: "0 0 4px" }}>{file.name}</p>
            <p style={{ fontSize: 12, color: "var(--ink-secondary)", margin: "0 0 16px" }}>
              {(file.size / 1024 / 1024 / 1024).toFixed(1)}GB
            </p>

            {waitingForWifi && !progress && (
              <div
                style={{
                  background: "var(--sand-soft)",
                  borderRadius: 12,
                  padding: 12,
                  fontSize: 12,
                  lineHeight: 1.6,
                }}
              >
                Wi-Fiを待っています。接続したら自動で送信します。
                <br />
                <button
                  onClick={() => {
                    setWaitingForWifi(false);
                    startUpload(file);
                  }}
                  style={{
                    marginTop: 6,
                    background: "none",
                    border: "none",
                    color: "var(--court)",
                    fontWeight: 700,
                    padding: 0,
                    fontSize: 12,
                  }}
                >
                  モバイル回線で今すぐ送る →
                </button>
              </div>
            )}

            {progress && progress.status !== "error" && (
              <>
                <div style={{ height: 8, background: "var(--sand-soft)", borderRadius: 4, overflow: "hidden", marginBottom: 10 }}>
                  <div style={{ height: "100%", width: `${pct}%`, background: "var(--court)", borderRadius: 4 }} />
                </div>
                <p style={{ fontSize: 12, color: "var(--ink-secondary)", margin: 0 }}>
                  {progress.status === "completed"
                    ? "受け取りました。解析をはじめます"
                    : `送信中 ${pct}% — アプリを閉じても続きます`}
                </p>
              </>
            )}

            {(error || progress?.status === "error") && (
              <div style={{ marginTop: 10 }}>
                <p style={{ fontSize: 12, color: "var(--alert)", margin: "0 0 8px" }}>
                  送信できませんでした（{error || progress?.message}）。
                </p>
                <button
                  onClick={() => startUpload(file)}
                  style={{
                    padding: "8px 16px",
                    borderRadius: 8,
                    border: "none",
                    background: "var(--court)",
                    color: "#fff",
                    fontWeight: 700,
                    fontSize: 12,
                  }}
                >
                  もう一度試す
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
