import csv
import sqlite3

import pytest

from src.db import database
from src.db.migrations import get_schema_version
from src.export.exporter import (
    EXPORT_SCHEMA_VERSION, build_metadata, is_valid_dataset_name, validate_export,
)


class Row(dict):
    """Stands in for sqlite3.Row, which supports keys() and [] access."""


@pytest.mark.parametrize("name,ok", [
    ("dataset", True), ("dataset_IPN", True), ("dataset_My-Source2", True),
    ("dataset_", False), ("IPN", False), ("dataset/IPN", False), ("dataset IPN", False),
    ("../dataset", False), ("", False),
])
def test_dataset_names(name, ok):
    assert is_valid_dataset_name(name) is ok


def test_migration_adds_source_path(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    database.init_db()
    conn = sqlite3.connect(tmp_path / "t.db")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)")]
    assert "source_path" in cols and "dataset" in cols
    assert get_schema_version(conn) == 4


def _write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_validate_uses_landmark_rows_not_video_header(tmp_path):
    video = tmp_path / "video.avi"
    video.write_bytes(b"x")
    landmarks = tmp_path / "landmarks.csv"
    labels = tmp_path / "labels.csv"
    _write(landmarks, ["frame_index"], [[i] for i in range(10)])
    _write(labels, ["frame_index", "label"], [[i, "writing"] for i in range(12)])
    session = Row(video_path=str(video), landmarks_path=str(landmarks), labels_path=str(labels))

    warnings = validate_export(session, total_frames=12)   # header says 12
    assert any("landmarks.csv has 10 rows" in w for w in warnings)

    _write(labels, ["frame_index", "label"], [[i, "maybe"] for i in range(10)])
    assert any("Unknown labels" in w for w in validate_export(session))


def test_metadata_records_resolution_timing_and_labels(tmp_path):
    landmarks = tmp_path / "landmarks.csv"
    labels = tmp_path / "labels.csv"
    _write(landmarks, ["frame_index", "l0_x", "handedness", "wl0_x"], [[0, 0.1, "Right", 0.0]])
    _write(labels, ["frame_index", "label"], [[0, "writing"], [1, "unsure"]])
    session = Row(id=7, dataset="dataset_Test", source_path="/downloads/clip_03.mp4",
                  lighting="normal", background="plain", dominant_hand="right",
                  date_created="2026-09-11", status="annotated", notes="", video_path=None)
    report = {"total_frames": 2, "pct_detected": 50.0,
              "video": {"width": 1080, "height": 1920, "fps": 60.0, "aspect": 0.5625},
              "timing": {"source": "container"}, "extraction": {"running_mode": "VIDEO"}}

    meta = build_metadata(session, {"participant_code": "P042"}, report,
                          str(landmarks), str(labels))

    assert meta["schema_version"] == EXPORT_SCHEMA_VERSION
    assert meta["session_id"] == "S007" and meta["participant_id"] == "P042"
    assert meta["dataset"] == "dataset_Test"
    assert meta["source_file"] == "clip_03.mp4"
    assert meta["video"]["width"] == 1080 and meta["video"]["height"] == 1920
    assert meta["landmark_columns"]["world"] and meta["landmark_columns"]["handedness"]
    assert meta["labels"]["counts"] == {"writing": 1, "unsure": 1}
    assert meta["labels"]["excluded_from_training"] == ["unsure"]
