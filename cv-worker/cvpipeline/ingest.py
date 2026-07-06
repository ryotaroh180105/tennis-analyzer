"""ingest正規化（02 §取り込み正規化）。

- 回転メタデータを正規化（表示済み回転で出力し、出力側のrotateは0にする）
- HEVC/HDR → H.264/SDR へ1回トランスコード（hls.js再生互換のため必須）
- GOP 2秒・目標ビットレート8Mbps（`-c copy`外側スナップの精度を支える。02のRound2修正）
- CFR化（CV入力の前提。時刻はPTS基準で保持されるようffmpegの-vsync cfrに委ねる）

簡略化注記：設計は「正規化済みH.264」と「CV用CFRプロキシ」を別ファイルとして
想定しているが、Phase 0では単一のCFR・H.264出力を編集元とCV入力の両方に使う
（両者の要件を満たすため実害はない。将来分離する場合はここを差し替える）。
"""

import subprocess

from cvpipeline.video_io import ffprobe


def normalize(input_path: str, output_path: str, encoder: str, gop_seconds: int, bitrate: str) -> dict:
    meta = ffprobe(input_path)
    target_fps = min(30.0, meta["fps"] or 30.0) or 30.0
    gop_frames = max(1, round(gop_seconds * target_fps))

    vf_filters = []
    if meta.get("is_hdr"):
        # HDR(HLG/PQ) -> SDR トーンマップ（02: この場合-c copy不可を許容。tonemap前提でlibzimgが必要）
        vf_filters.append(
            "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
        )

    cmd = ["ffmpeg", "-y", "-i", input_path]

    if vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]

    cmd += [
        "-r",
        str(target_fps),
        "-vsync",
        "cfr",
        "-c:v",
        encoder,
        "-g",
        str(gop_frames),
        "-forced-idr",
        "1" if encoder == "libx264" else "0",
        "-b:v",
        bitrate,
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-metadata:s:v:0",
        "rotate=0",
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)

    out_meta = ffprobe(output_path)
    return {"input_meta": meta, "output_meta": out_meta, "gop_frames": gop_frames}
