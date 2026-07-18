"""Convert sequentially-named image frames (WITA / IPN PNG samples) into a
video file the normal pipeline can process."""

import re
from pathlib import Path
from typing import Callable

import cv2
from PySide6.QtCore import QThread, Signal

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"}


def _natural_key(path: Path):
    # frame_2 sorts before frame_10 even without zero-padding
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", path.name)]


def list_sequence(folder: str | Path) -> list[Path]:
    """Image files in the folder, in natural frame order."""
    folder = Path(folder)
    frames = [p for p in folder.iterdir()
              if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    return sorted(frames, key=_natural_key)


def find_sequences(folder: str | Path) -> list[Path]:
    """Sequence folders under `folder`: itself if it holds images directly,
    otherwise every direct subfolder that does."""
    folder = Path(folder)
    if list_sequence(folder):
        return [folder]
    return sorted(
        d for d in folder.iterdir() if d.is_dir() and list_sequence(d)
    )


def sequence_to_video(
    folder: str | Path,
    out_path: str | Path,
    fps: float,
    progress_cb: Callable[[int, int], None] | None = None,
) -> int:
    """Write the folder's image sequence to a video. Returns frame count."""
    frames = list_sequence(folder)
    if not frames:
        raise ValueError(f"No image frames found in {folder}")

    first = cv2.imread(str(frames[0]))
    if first is None:
        raise ValueError(f"Cannot read image: {frames[0]}")
    h, w = first.shape[:2]

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
    try:
        for i, frame_path in enumerate(frames):
            img = cv2.imread(str(frame_path))
            if img is None:
                continue
            if img.shape[:2] != (h, w):
                img = cv2.resize(img, (w, h))
            writer.write(img)
            if progress_cb:
                progress_cb(i + 1, len(frames))
    finally:
        writer.release()
    return len(frames)


class SequenceConverterThread(QThread):
    progress = Signal(int, int)   # current_frame, total_frames
    finished = Signal(str)        # output video path
    error = Signal(str)

    def __init__(self, folder: str, out_path: str, fps: float):
        super().__init__()
        self._folder = folder
        self._out_path = out_path
        self._fps = fps

    def run(self):
        try:
            sequence_to_video(
                self._folder, self._out_path, self._fps,
                progress_cb=lambda cur, total: self.progress.emit(cur, total),
            )
            self.finished.emit(self._out_path)
        except Exception as exc:
            self.error.emit(str(exc))
