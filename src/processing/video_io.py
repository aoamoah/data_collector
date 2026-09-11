"""Frame-exact video access shared by extraction and annotation.

Labels are only as good as the agreement between the frame an annotator sees
and the frame the extractor wrote landmarks for. Two things break that
agreement on sources the collector did not record itself:

- **Seeking is not frame-exact.** OpenCV seeks by container entry, not by
  decoded frame. Measured on IPN `.avi` files, which contain dropped-frame
  entries: asking for frame 3207 shows decoded frame 3194, and the error grows
  along the video. The extractor reads sequentially and is correct, so the
  annotation screen was the side that drifted — up to ~14 frames (~0.45 s),
  longer than a typical pause inside a letter.
- **The header frame count is an estimate.** On the same files it overstates
  the decodable frames by up to 21.

The fix is an annotation proxy: while the extractor decodes the source
sequentially, it writes every decoded frame into a fresh MP4. Frame *i* of the
proxy is by construction frame *i* of `landmarks.csv`, and an OpenCV-written
MP4 seeks exactly. The proxy is also downscaled, so a 4K source annotates as
smoothly as a webcam one. It is a viewing aid only — never exported, never
used for extraction.

Timing: a webcam that cannot sustain the requested rate (dim light) still
gets written at the nominal fps, so container timestamps would claim 30 fps
for footage captured at 20. The recorder therefore logs real capture times
to a sidecar, and extraction prefers it.
"""

import csv
from pathlib import Path

import cv2

PROXY_NAME = "annotation_proxy.mp4"
CAPTURE_TIMESTAMPS_NAME = "capture_timestamps.csv"
PROXY_MAX_SIDE = 960


def probe_video(video_path: str | Path) -> dict:
    """Container-reported properties. frame count and fps are estimates for
    some containers; the extractor records the decoded count separately."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    try:
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        return {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": round(fps, 3) if fps > 0 else None,
            "header_frames": max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))),
            "fourcc": fourcc.to_bytes(4, "little").decode("ascii", "replace").strip("\x00")
            if fourcc > 0 else None,
        }
    finally:
        cap.release()


def proxy_size(width: int, height: int, max_side: int = PROXY_MAX_SIDE) -> tuple[int, int]:
    """Downscaled (w, h) preserving aspect, even dimensions for the encoder."""
    scale = min(1.0, max_side / max(width, height))
    w = max(2, int(round(width * scale)) // 2 * 2)
    h = max(2, int(round(height * scale)) // 2 * 2)
    return w, h


def proxy_path_for(landmarks_path: str | Path | None) -> Path | None:
    """The proxy lives next to the session's landmarks.csv."""
    if not landmarks_path:
        return None
    return Path(landmarks_path).parent / PROXY_NAME


def capture_timestamps_path_for(video_path: str | Path) -> Path:
    return Path(video_path).parent / CAPTURE_TIMESTAMPS_NAME


def save_capture_timestamps(path: str | Path, timestamps_ms: list[float]):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_index", "timestamp_ms"])
        for i, t in enumerate(timestamps_ms):
            writer.writerow([i, round(t, 3)])


def load_capture_timestamps(video_path: str | Path) -> list[float] | None:
    """Real per-frame capture times logged by the recorder, if present."""
    path = capture_timestamps_path_for(video_path)
    if not path.exists():
        return None
    with open(path, newline="") as f:
        return [float(row["timestamp_ms"]) for row in csv.DictReader(f)]
