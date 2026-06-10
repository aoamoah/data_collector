import os
import sys
import time
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from src.processing.model_utils import model_path

# Suppress OpenCV verbose backend probing logs
os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")

_CAM_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2

# MediaPipe hand skeleton connections for live overlay
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]


def find_available_camera() -> int | None:
    """Return the first working camera index, or None if none found."""
    for index in range(4):
        cap = cv2.VideoCapture(index, _CAM_BACKEND)
        if cap.isOpened():
            cap.release()
            return index
        cap.release()
    return None


class CameraThread(QThread):
    frame_ready = Signal(QImage, float)   # frame, fps
    hand_presence = Signal(bool)          # hand detected in frame
    error = Signal(str)

    def __init__(self, camera_index: int = 0, resolution: tuple = (640, 480), fps: int = 30, dominant_hand: str = "right"):
        super().__init__()
        self._camera_index = camera_index
        self._width, self._height = resolution
        self._fps = fps
        self._recording = False
        self._writer: cv2.VideoWriter | None = None
        self._running = False
        self._output_path: str = ""
        self._dominant_hand = dominant_hand.capitalize()  # "Right" or "Left"

    def start_recording(self, output_path: str, fps: float, width: int, height: int):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        self._output_path = output_path
        self._recording = True

    def stop_recording(self) -> str:
        self._recording = False
        if self._writer:
            self._writer.release()
            self._writer = None
        return self._output_path

    def stop(self):
        self._running = False
        self.wait()

    def run(self):
        cap = cv2.VideoCapture(self._camera_index, _CAM_BACKEND)
        if not cap.isOpened():
            self.error.emit("Cannot open camera")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_FPS, self._fps)

        # Set up MediaPipe for live hand detection (IMAGE mode, runs every N frames)
        # Only runs if the model file is already downloaded
        landmarker = None
        _model = model_path()
        if _model.exists():
            try:
                options = mp_vision.HandLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(_model)),
                    running_mode=mp_vision.RunningMode.IMAGE,
                    num_hands=2,
                    min_hand_detection_confidence=0.5,
                    min_hand_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                landmarker = mp_vision.HandLandmarker.create_from_options(options)
            except Exception:
                landmarker = None

        self._running = True
        prev_time = time.time()
        fps = 0.0
        frame_count = 0
        _last_hand_detected = False
        _last_landmarks = None  # list of landmark lists from last detection

        while self._running:
            ret, frame = cap.read()
            if not ret:
                self.error.emit("Failed to read frame")
                break

            if self._recording and self._writer:
                self._writer.write(frame)

            now = time.time()
            elapsed = now - prev_time
            fps = 1.0 / elapsed if elapsed > 0 else fps
            prev_time = now

            # Run hand detection every 5 frames
            if landmarker and frame_count % 5 == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect(mp_image)
                # Keep only the dominant hand when multiple hands are detected
                filtered = [
                    lms for lms, handedness in zip(result.hand_landmarks, result.handedness)
                    if handedness and handedness[0].category_name == self._dominant_hand
                ]
                detected = bool(filtered)
                _last_landmarks = filtered if detected else None
                if detected != _last_hand_detected:
                    self.hand_presence.emit(detected)
                    _last_hand_detected = detected

            preview = cv2.flip(frame, 1)

            # Draw landmark skeleton on preview (recorded video stays clean)
            if _last_landmarks:
                ph, pw = preview.shape[:2]
                for hand_lms in _last_landmarks:
                    pts = [
                        (int((1.0 - lm.x) * pw), int(lm.y * ph))
                        for lm in hand_lms
                    ]
                    for a, b in HAND_CONNECTIONS:
                        cv2.line(preview, pts[a], pts[b], (0, 255, 0), 2)
                    for px, py in pts:
                        cv2.circle(preview, (px, py), 4, (0, 200, 255), -1)

            rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            self.frame_ready.emit(image.copy(), fps)
            frame_count += 1

        cap.release()
        if landmarker:
            landmarker.close()
        if self._writer:
            self._writer.release()
            self._writer = None
