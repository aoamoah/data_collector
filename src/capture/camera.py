import os
import time
import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

# Suppress OpenCV verbose backend probing logs
os.environ.setdefault("OPENCV_LOG_LEVEL", "OFF")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")


def find_available_camera() -> int | None:
    """Return the first working camera index, or None if none found."""
    for index in range(4):
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if cap.isOpened():
            cap.release()
            return index
        cap.release()
    return None


class CameraThread(QThread):
    frame_ready = Signal(QImage, float)   # frame, fps
    error = Signal(str)

    def __init__(self, camera_index: int = 0):
        super().__init__()
        self._camera_index = camera_index
        self._recording = False
        self._writer: cv2.VideoWriter | None = None
        self._running = False
        self._output_path: str = ""

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
        cap = cv2.VideoCapture(self._camera_index, cv2.CAP_V4L2)
        if not cap.isOpened():
            self.error.emit("Cannot open camera")
            return

        self._running = True
        prev_time = time.time()
        fps = 0.0

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

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            self.frame_ready.emit(image.copy(), fps)

        cap.release()
        if self._writer:
            self._writer.release()
            self._writer = None
