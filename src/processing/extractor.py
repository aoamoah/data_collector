import csv
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
from PySide6.QtCore import QThread, Signal


LANDMARK_HEADERS = (
    ["frame_index", "timestamp_ms", "hand_detected", "detection_confidence", "tracking_confidence"]
    + [f"l{i}_{axis}" for i in range(21) for axis in ("x", "y", "z")]
)


class ExtractorThread(QThread):
    progress = Signal(int, int)   # current_frame, total_frames
    finished = Signal(str)        # output csv path
    error = Signal(str)

    def __init__(self, video_path: str, output_csv: str):
        super().__init__()
        self._video_path = video_path
        self._output_csv = output_csv

    def run(self):
        try:
            extract_landmarks(
                self._video_path,
                self._output_csv,
                progress_cb=lambda cur, total: self.progress.emit(cur, total),
            )
            self.finished.emit(self._output_csv)
        except Exception as exc:
            self.error.emit(str(exc))


def extract_landmarks(
    video_path: str,
    output_csv: str,
    progress_cb: Callable[[int, int], None] | None = None,
):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)

    hands = mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(LANDMARK_HEADERS)

        frame_index = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            if result.multi_hand_landmarks and result.multi_handedness:
                lm = result.multi_hand_landmarks[0].landmark
                handedness = result.multi_handedness[0].classifications[0]
                row = (
                    [frame_index, round(timestamp_ms, 2), True,
                     round(handedness.score, 4), round(handedness.score, 4)]
                    + [round(getattr(p, axis), 6) for p in lm for axis in ("x", "y", "z")]
                )
            else:
                row = [frame_index, round(timestamp_ms, 2), False, 0.0, 0.0] + [0.0] * 63

            writer.writerow(row)
            frame_index += 1

            if progress_cb:
                progress_cb(frame_index, total)

    cap.release()
    hands.close()
