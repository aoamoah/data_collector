import csv
import hashlib
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from PySide6.QtCore import QThread, Signal

from src.processing.hand_selection import select_hand_index
from src.processing.model_utils import ensure_model
from src.processing.quality import FrameQuality, compute_quality_report
from src.processing.video_io import (
    load_capture_timestamps, probe_video, proxy_size,
)

# Image landmarks l*_ are fractions of frame width (x) and height (y), so
# their scale depends on the video's aspect ratio. World landmarks wl*_ are
# MediaPipe's metric 3D estimate in metres, centred on the hand — independent
# of resolution and aspect by construction, but without the hand's position
# in the frame. Both are written; the trainer decides which to use. New
# columns are appended so readers that select by name are unaffected.
LANDMARK_HEADERS = (
    ["frame_index", "timestamp_ms", "hand_detected", "detection_confidence", "tracking_confidence"]
    + [f"l{i}_{axis}" for i in range(21) for axis in ("x", "y", "z")]
    + ["handedness"]
    + [f"wl{i}_{axis}" for i in range(21) for axis in ("x", "y", "z")]
)

MIN_DETECTION_CONFIDENCE = 0.5
MIN_PRESENCE_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5
NUM_HANDS = 2


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
        proxy_path: str | None = None,
    ):
        super().__init__()
        self._video_path = video_path
        self._output_csv = output_csv
        self._confidence_threshold = confidence_threshold
        self._target_hand = target_hand
        self._proxy_path = proxy_path

    def run(self):
        try:
            report = extract_landmarks(
                self._video_path,
                self._output_csv,
                confidence_threshold=self._confidence_threshold,
                target_hand=self._target_hand,
                proxy_path=self._proxy_path,
                progress_cb=lambda cur, total: self.progress.emit(cur, total),
            )
            self.quality_ready.emit(report)
            self.finished.emit(self._output_csv)
        except Exception as exc:
            self.error.emit(str(exc))


def _file_sha256(path: str, length: int = 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:length]


def extract_landmarks(
    video_path: str,
    output_csv: str,
    confidence_threshold: float = 0.0,
    target_hand: str = "right",
    proxy_path: str | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    """Extract landmarks of the target hand from video. Returns quality report dict.

    When `proxy_path` is given, every decoded frame is also written to a
    downscaled MP4 there, so the annotation screen can seek frame-exactly
    (see video_io).
    """
    info = probe_video(video_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = info["header_frames"]
    nominal_fps = info["fps"] or 30.0
    frame_ms = 1000.0 / nominal_fps
    capture_ts = load_capture_timestamps(video_path)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)

    model = ensure_model()
    options = mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=NUM_HANDS,
        min_hand_detection_confidence=MIN_DETECTION_CONFIDENCE,
        min_hand_presence_confidence=MIN_PRESENCE_CONFIDENCE,
        min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
    )

    frame_qualities: list[FrameQuality] = []
    last_ts: float | None = None
    last_mp_ts = -1
    timestamp_repairs = 0
    handedness_counts: dict[str, int] = {}
    proxy_writer = None
    empty_row_tail = [0.0] * 63 + [""] + [0.0] * 63

    try:
        with open(output_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(LANDMARK_HEADERS)

            with mp_vision.HandLandmarker.create_from_options(options) as landmarker:
                frame_index = 0
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    if proxy_path:
                        if proxy_writer is None:
                            h, w = frame.shape[:2]
                            size = proxy_size(w, h)
                            Path(proxy_path).parent.mkdir(parents=True, exist_ok=True)
                            proxy_writer = cv2.VideoWriter(
                                str(proxy_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                nominal_fps, size)
                        proxy_writer.write(cv2.resize(frame, size, interpolation=cv2.INTER_AREA))

                    # Real capture time when the recorder logged it; otherwise
                    # the container's. Either must be strictly increasing —
                    # MediaPipe VIDEO mode raises on repeats, and a zero dt
                    # would divide the trainer's speeds by zero — so a stalled
                    # clock is advanced by one nominal frame instead of the
                    # frame being skipped. (Skipping silently marked every
                    # frame undetected on containers whose clock never moves.)
                    if capture_ts is not None and frame_index < len(capture_ts):
                        ts = capture_ts[frame_index]
                    else:
                        ts = cap.get(cv2.CAP_PROP_POS_MSEC)
                    if last_ts is not None and ts <= last_ts:
                        ts = last_ts + frame_ms
                        timestamp_repairs += 1
                    last_ts = ts
                    # Truncated, as the extractor always has: VIDEO-mode tracking
                    # smooths using these timestamps, so rounding instead would
                    # shift landmarks against sessions extracted earlier
                    # max() keeps whole milliseconds strictly increasing even if
                    # the clock advanced by less than one
                    timestamp_ms = max(int(ts), last_mp_ts + 1)
                    last_mp_ts = timestamp_ms

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(mp_image, timestamp_ms)

                    picked = select_hand_index(
                        result.hand_landmarks, result.handedness, target_hand)
                    # HandLandmarker exposes only the handedness classification
                    # score per hand; it fills both confidence columns.
                    confidence = round(picked[1], 4) if picked else 0.0
                    if picked and confidence >= confidence_threshold:
                        index, _, label = picked
                        lm = result.hand_landmarks[index]
                        world = (result.hand_world_landmarks[index]
                                 if index < len(result.hand_world_landmarks) else None)
                        row = (
                            [frame_index, timestamp_ms, True, confidence, confidence]
                            + [round(getattr(p, axis), 6) for p in lm for axis in ("x", "y", "z")]
                            + [label or ""]
                            + ([round(getattr(p, axis), 6) for p in world for axis in ("x", "y", "z")]
                               if world else [0.0] * 63)
                        )
                        handedness_counts[label or "?"] = handedness_counts.get(label or "?", 0) + 1
                        frame_qualities.append(
                            FrameQuality(frame_index, timestamp_ms, confidence, True, False))
                    else:
                        row = [frame_index, timestamp_ms, False, 0.0, 0.0] + empty_row_tail
                        frame_qualities.append(
                            FrameQuality(frame_index, timestamp_ms, confidence, False, False))

                    writer.writerow(row)
                    frame_index += 1

                    if progress_cb:
                        progress_cb(frame_index, total)
    finally:
        cap.release()
        if proxy_writer is not None:
            proxy_writer.release()

    decoded = len(frame_qualities)
    report = compute_quality_report(frame_qualities)
    report["duplicate_frames"] = timestamp_repairs
    report["video"] = {
        **info,
        "decoded_frames": decoded,
        "aspect": round(info["width"] / info["height"], 6) if info["height"] else None,
    }
    if capture_ts is not None:
        timing_source = "capture_log"
    else:
        timing_source = "container"
    report["timing"] = {
        "source": timing_source,
        "capture_log_frames": len(capture_ts) if capture_ts is not None else None,
        "timestamp_repairs": timestamp_repairs,
        "measured_fps": (round(1000.0 * (decoded - 1) / (frame_qualities[-1].timestamp_ms
                                                        - frame_qualities[0].timestamp_ms), 3)
                         if decoded > 1 and frame_qualities[-1].timestamp_ms
                         > frame_qualities[0].timestamp_ms else None),
    }
    report["extraction"] = {
        "mediapipe_version": mp.__version__,
        "model_sha256": _file_sha256(model),
        "running_mode": "VIDEO",
        "num_hands": NUM_HANDS,
        "min_hand_detection_confidence": MIN_DETECTION_CONFIDENCE,
        "min_hand_presence_confidence": MIN_PRESENCE_CONFIDENCE,
        "min_tracking_confidence": MIN_TRACKING_CONFIDENCE,
        "target_hand": target_hand,
        "confidence_threshold": confidence_threshold,
        "handedness_counts": handedness_counts,
        "proxy_written": bool(proxy_path and proxy_writer is not None),
    }
    return report
