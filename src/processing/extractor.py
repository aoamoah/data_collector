import csv
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from PySide6.QtCore import QThread, Signal

from src.processing.model_utils import ensure_model
from src.processing.quality import FrameQuality, compute_quality_report


LANDMARK_HEADERS = (
    ["frame_index", "timestamp_ms", "hand_detected", "detection_confidence", "tracking_confidence"]
    + [f"l{i}_{axis}" for i in range(21) for axis in ("x", "y", "z")]
)


class ExtractorThread(QThread):
    progress = Signal(int, int)   # current_frame, total_frames
    finished = Signal(str)        # output csv path
    quality_ready = Signal(dict)  # quality report dict
    error = Signal(str)

    def __init__(self, video_path: str, output_csv: str, confidence_threshold: float = 0.0):
        super().__init__()
        self._video_path = video_path
        self._output_csv = output_csv
        self._confidence_threshold = confidence_threshold

    def run(self):
        try:
            report = extract_landmarks(
                self._video_path,
                self._output_csv,
                confidence_threshold=self._confidence_threshold,
                progress_cb=lambda cur, total: self.progress.emit(cur, total),
            )
            self.quality_ready.emit(report)
            self.finished.emit(self._output_csv)
        except Exception as exc:
            self.error.emit(str(exc))


def extract_landmarks(
    video_path: str,
    output_csv: str,
    confidence_threshold: float = 0.0,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    """Extract hand landmarks from video. Returns quality report dict."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)

    options = mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=ensure_model()),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frame_qualities: list[FrameQuality] = []
    seen_timestamps: set[int] = set()

    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(LANDMARK_HEADERS)

        with mp_vision.HandLandmarker.create_from_options(options) as landmarker:
            frame_index = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                timestamp_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))

                # Duplicate frame detection
                is_duplicate = timestamp_ms in seen_timestamps and frame_index > 0
                if not is_duplicate:
                    seen_timestamps.add(timestamp_ms)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(mp_image, timestamp_ms)

                if result.hand_landmarks and result.handedness and not is_duplicate:
                    lm = result.hand_landmarks[0]
                    confidence = round(result.handedness[0][0].score, 4)

                    # Apply confidence threshold filtering
                    if confidence >= confidence_threshold:
                        row = (
                            [frame_index, timestamp_ms, True, confidence, confidence]
                            + [round(getattr(p, axis), 6) for p in lm for axis in ("x", "y", "z")]
                        )
                        frame_qualities.append(
                            FrameQuality(frame_index, timestamp_ms, confidence, True, False)
                        )
                    else:
                        row = [frame_index, timestamp_ms, False, 0.0, 0.0] + [0.0] * 63
                        frame_qualities.append(
                            FrameQuality(frame_index, timestamp_ms, confidence, False, False)
                        )
                else:
                    row = [frame_index, timestamp_ms, False, 0.0, 0.0] + [0.0] * 63
                    frame_qualities.append(
                        FrameQuality(frame_index, timestamp_ms, 0.0, False, is_duplicate)
                    )

                writer.writerow(row)
                frame_index += 1

                if progress_cb:
                    progress_cb(frame_index, total)

    cap.release()
    return compute_quality_report(frame_qualities)
