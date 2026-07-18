import csv
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from PySide6.QtCore import QThread, Signal

from src.processing.hand_selection import select_hand
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

    def __init__(
        self,
        video_path: str,
        output_csv: str,
        confidence_threshold: float = 0.0,
        target_hand: str = "right",
    ):
        super().__init__()
        self._video_path = video_path
        self._output_csv = output_csv
        self._confidence_threshold = confidence_threshold
        self._target_hand = target_hand

    def run(self):
        try:
            report = extract_landmarks(
                self._video_path,
                self._output_csv,
                confidence_threshold=self._confidence_threshold,
                target_hand=self._target_hand,
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
    target_hand: str = "right",
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    """Extract landmarks of the target hand from video. Returns quality report dict."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)

    options = mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=ensure_model()),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    frame_qualities: list[FrameQuality] = []
    last_timestamp = -1

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

                # MediaPipe VIDEO mode requires strictly increasing timestamps
                # and raises on repeats, so duplicate/non-monotonic frames are
                # recorded as undetected without running detection.
                is_duplicate = frame_index > 0 and timestamp_ms <= last_timestamp

                result = None
                if not is_duplicate:
                    last_timestamp = timestamp_ms
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(mp_image, timestamp_ms)

                selected = None
                if result:
                    selected = select_hand(
                        result.hand_landmarks, result.handedness, target_hand
                    )

                if selected:
                    # HandLandmarker exposes only the handedness classification
                    # score per hand; it fills both confidence columns.
                    lm, score = selected
                    confidence = round(score, 4)

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
