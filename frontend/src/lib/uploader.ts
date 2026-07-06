/**
 * マルチパートアップロード（中断・再開対応）。09/10のRound2修正：
 * ETagはクライアントに持たせない — completeはサーバーがR2 ListPartsで組み立てる。
 * localStorageにupload_idと完了パート数を永続化し、再起動後もGET /api/uploads/{id}と
 * 突き合わせて再開する（iOS Safariのタブ切替・画面ロックでの中断が常態のため）。
 */

import { api } from "./api";

const STORAGE_KEY = "tennis-analyzer:pending-upload";

interface PendingUpload {
  uploadId: string;
  filename: string;
  totalSize: number;
  partSize: number;
}

export interface UploadProgress {
  uploadedBytes: number;
  totalBytes: number;
  status: "uploading" | "completed" | "error";
  message?: string;
}

function savePending(p: PendingUpload) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
}

function loadPending(): PendingUpload | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw ? JSON.parse(raw) : null;
}

function clearPending() {
  localStorage.removeItem(STORAGE_KEY);
}

export function getResumableUpload(): PendingUpload | null {
  return loadPending();
}

export async function uploadFile(
  file: File,
  onProgress: (p: UploadProgress) => void
): Promise<string> {
  let pending = loadPending();
  let uploadId: string;
  let partSize: number;

  if (pending && pending.filename === file.name && pending.totalSize === file.size) {
    uploadId = pending.uploadId;
    partSize = pending.partSize;
  } else {
    const created = await api.createUpload(file.name, file.size, file.type || "video/mp4");
    uploadId = created.upload_id;
    partSize = created.part_size;
    pending = { uploadId, filename: file.name, totalSize: file.size, partSize };
    savePending(pending);
  }

  const totalParts = Math.ceil(file.size / partSize);

  // 再開：完了済みパートを問い合わせる
  const status = await api.getUploadStatus(uploadId);
  const completedSet = new Set(status.completed_parts.map((p) => p.part_number));

  const remainingParts = [];
  for (let i = 1; i <= totalParts; i++) {
    if (!completedSet.has(i)) remainingParts.push(i);
  }

  let uploadedBytes = (totalParts - remainingParts.length) * partSize;
  onProgress({ uploadedBytes, totalBytes: file.size, status: "uploading" });

  if (remainingParts.length > 0) {
    const { urls } = await api.getPartUrls(uploadId, remainingParts);

    for (const partNumber of remainingParts) {
      const start = (partNumber - 1) * partSize;
      const end = Math.min(start + partSize, file.size);
      const chunk = file.slice(start, end);

      const url = urls[String(partNumber)] ?? urls[partNumber as unknown as string];
      const res = await fetch(url, { method: "PUT", body: chunk });
      if (!res.ok) {
        onProgress({ uploadedBytes, totalBytes: file.size, status: "error", message: "通信が不安定です" });
        throw new Error(`part upload failed: ${partNumber}`);
      }

      uploadedBytes += chunk.size;
      onProgress({ uploadedBytes, totalBytes: file.size, status: "uploading" });
    }
  }

  await api.completeUpload(uploadId);
  clearPending();
  onProgress({ uploadedBytes: file.size, totalBytes: file.size, status: "completed" });
  return uploadId;
}

export function isOnWifi(): boolean {
  const conn = (navigator as any).connection;
  if (!conn) return true; // 判定不能なら送信を許可する
  if (conn.type) return conn.type === "wifi";
  return conn.effectiveType === "4g";
}
