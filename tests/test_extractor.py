"""Extraction on synthetic videos. There are no hands in them, so these check
the plumbing — columns, frame counts, timing, the proxy — not detection."""

import csv

import cv2
import numpy as np
import pytest

from src.processing.extractor import LANDMARK_HEADERS, extract_landmarks
from src.processing.video_io import (
    capture_timestamps_path_for, proxy_size, save_capture_timestamps,
)


def _write_numbered_video(path, n, size, fps=30.0):
    """Each frame carries its index as a brightness pattern, so a frame read
    back can be identified exactly."""
    w, h = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(n):
        frame = np.zeros((h, w, 3), np.uint8)
        frame[:, :, 0] = (i * 7) % 256
        frame[:, :, 1] = (i * 13) % 256
        cv2.putText(frame, str(i), (10, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        writer.write(frame)
    writer.release()


def _read_all(path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f.astype(np.int16))
    cap.release()
    return frames


def _rows(csv_path):
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("size", [(640, 480), (464, 832)])   # landscape and portrait
def test_extraction_writes_all_columns_and_a_frame_exact_proxy(tmp_path, size):
    video = tmp_path / "video.mp4"
    _write_numbered_video(video, 45, size)
    out_csv = tmp_path / "landmarks.csv"
    proxy = tmp_path / "annotation_proxy.mp4"

    report = extract_landmarks(str(video), str(out_csv), proxy_path=str(proxy))

    rows = _rows(out_csv)
    with open(out_csv, newline="") as f:
        assert next(csv.reader(f)) == LANDMARK_HEADERS
    assert len(rows) == 45
    assert [int(r["frame_index"]) for r in rows] == list(range(45))
    ts = [int(r["timestamp_ms"]) for r in rows]
    assert all(b > a for a, b in zip(ts, ts[1:]))

    assert (report["video"]["width"], report["video"]["height"]) == size
    assert report["video"]["decoded_frames"] == 45
    assert report["timing"]["source"] == "container"
    assert report["extraction"]["proxy_written"]

    # The proxy holds exactly the decoded frames, and seeking it lands on the
    # frame asked for — the property the annotation screen depends on
    cap = cv2.VideoCapture(str(proxy))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 45
    assert (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) == proxy_size(*size)
    sequential = _read_all(proxy)
    for i in (0, 1, 17, 30, 44):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        assert ok
        diffs = [np.abs(f.astype(np.int16) - s).mean() for s in sequential]
        assert int(np.argmin(diffs)) == i
    cap.release()


def test_capture_log_overrides_container_timing(tmp_path):
    video = tmp_path / "video.mp4"
    _write_numbered_video(video, 10, (320, 240), fps=30.0)
    # The camera actually delivered 20 fps; the container claims 30
    real = [i * 50.0 for i in range(10)]
    save_capture_timestamps(capture_timestamps_path_for(video), real)

    out_csv = tmp_path / "landmarks.csv"
    report = extract_landmarks(str(video), str(out_csv))

    assert [int(r["timestamp_ms"]) for r in _rows(out_csv)] == [int(t) for t in real]
    assert report["timing"]["source"] == "capture_log"
    assert report["timing"]["measured_fps"] == pytest.approx(20.0)


def test_stalled_clock_is_repaired_not_skipped(tmp_path):
    video = tmp_path / "video.mp4"
    _write_numbered_video(video, 6, (320, 240))
    save_capture_timestamps(capture_timestamps_path_for(video), [0, 33, 33, 33, 133, 166])

    out_csv = tmp_path / "landmarks.csv"
    report = extract_landmarks(str(video), str(out_csv))

    ts = [int(r["timestamp_ms"]) for r in _rows(out_csv)]
    assert all(b > a for a, b in zip(ts, ts[1:]))
    assert report["timing"]["timestamp_repairs"] == 2


def test_proxy_size_keeps_aspect_and_even_dimensions():
    assert proxy_size(640, 480) == (640, 480)
    w, h = proxy_size(3840, 2160)
    assert max(w, h) <= 960 and w % 2 == 0 and h % 2 == 0
    assert abs(w / h - 3840 / 2160) < 0.01
    w, h = proxy_size(1080, 1920)
    assert h == 960 and w % 2 == 0
