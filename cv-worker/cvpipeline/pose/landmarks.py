"""MediaPipe Pose Landmarker（Tasks API、Apache-2.0・事前学習済みモデル）での骨格系列抽出。

RT-DETR/TrackNet系と違い学習データ調達がボトルネックにならないため、他ステージの
「dev軽量代替CV」とは異なり実モデルをそのまま使う（05-tech-stack.md §CV）。

pose_world_landmarks（メートル単位・腰基準）を使う。pose_landmarks（画像正規化座標）は
カメラ距離に依存するため角度・比率算出には使わない（06 §正規化指標）。
ランドマークのvisibilityが低いフレームは該当指標を unknown として返す
（CLAUDE.md 不変原則1: 誤った断定より未分類を優先）。
"""

# 解析に使う12関節のみ（33点全ては保持しない。中間出力を軽量に保つ）
JOINT_LANDMARKS = {
    "left_shoulder": "LEFT_SHOULDER",
    "right_shoulder": "RIGHT_SHOULDER",
    "left_elbow": "LEFT_ELBOW",
    "right_elbow": "RIGHT_ELBOW",
    "left_wrist": "LEFT_WRIST",
    "right_wrist": "RIGHT_WRIST",
    "left_hip": "LEFT_HIP",
    "right_hip": "RIGHT_HIP",
    "left_knee": "LEFT_KNEE",
    "right_knee": "RIGHT_KNEE",
    "left_ankle": "LEFT_ANKLE",
    "right_ankle": "RIGHT_ANKLE",
}


def extract_landmarks(video_path: str, model_path: str, hz: float, max_seconds: float | None = None) -> list[dict]:
    """MediaPipe Pose Landmarker（VIDEO mode）でフレームごとの骨格ワールド座標を抽出する。"""
    import cv2
    import mediapipe as mp

    from cvpipeline.video_io import sample_frames

    base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    series: list[dict] = []
    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
        for t, frame in sample_frames(video_path, hz=hz, max_seconds=max_seconds):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(image, int(t * 1000))

            if not result.pose_world_landmarks:
                series.append({"t": round(t, 3), "joints": None, "visible_ratio": 0.0})
                continue

            world = result.pose_world_landmarks[0]
            joints = {}
            visibilities = []
            for name, landmark_attr in JOINT_LANDMARKS.items():
                idx = mp.tasks.vision.PoseLandmark[landmark_attr].value
                lm = world[idx]
                joints[name] = {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}
                visibilities.append(lm.visibility)

            series.append(
                {
                    "t": round(t, 3),
                    "joints": joints,
                    "visible_ratio": round(sum(visibilities) / len(visibilities), 3) if visibilities else 0.0,
                }
            )

    return series
