import csv
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from src.annotation.annotator import DEFAULT_LABEL, LABELS
from src.db.database import get_connection
from src.db.models import get_participant, get_quality_report, get_session
from src.db.paths import PROJECT_ROOT, resolve_data_path

# Bumped whenever metadata.json or the CSVs change shape, so the trainer can
# tell what a folder contains without guessing from its columns.
EXPORT_SCHEMA_VERSION = 2

# The starting set. Any other name matching DATASET_NAME_RE is accepted, so a
# new source is just a new folder: dataset_<Source>.
DATASET_FOLDERS = ["dataset", "dataset_WITA", "dataset_IPN"]
DATASET_NAME_RE = re.compile(r"^dataset(_[A-Za-z0-9][A-Za-z0-9-]*)?$")


def is_valid_dataset_name(name: str) -> bool:
    return bool(DATASET_NAME_RE.match(name or ""))


def known_datasets() -> list[str]:
    """Default folders plus every dataset name already used by a session."""
    with get_connection() as conn:
        used = [r[0] for r in conn.execute(
            "SELECT DISTINCT dataset FROM sessions WHERE dataset IS NOT NULL")]
    extra = sorted(n for n in used if n not in DATASET_FOLDERS and is_valid_dataset_name(n))
    return DATASET_FOLDERS + extra


def _count_rows(path: str) -> int:
    with open(path, newline="") as f:
        return max(0, sum(1 for _ in f) - 1)


def validate_export(session, total_frames: int = 0) -> list[str]:
    """Return a list of warning strings. Empty list means export is safe to proceed.

    Labels are checked against landmarks.csv, not the video header: the
    header frame count is an estimate on some containers (IPN .avi overstates
    it by up to 21 frames), while every landmarks row is a decoded frame."""
    warnings = []

    if not resolve_data_path(session["video_path"]):
        warnings.append("Video file is missing.")

    landmarks_path = resolve_data_path(session["landmarks_path"])
    if not landmarks_path:
        warnings.append("Landmarks CSV is missing.")

    labels_path = resolve_data_path(session["labels_path"])
    if not labels_path:
        warnings.append("Labels CSV is missing.")
    else:
        expected = _count_rows(landmarks_path) if landmarks_path else total_frames
        label_count = _count_rows(labels_path)
        if expected and label_count != expected:
            warnings.append(
                f"Labels cover {label_count} frames but landmarks.csv has {expected} rows.")
        with open(labels_path, newline="") as f:
            unknown = {row["label"] for row in csv.DictReader(f)} - set(LABELS)
        if unknown:
            warnings.append(f"Unknown labels in labels.csv: {', '.join(sorted(unknown))}.")

    return warnings


def _label_counts(labels_path: str | None) -> dict:
    if not labels_path:
        return {}
    with open(labels_path, newline="") as f:
        return dict(Counter(row["label"] for row in csv.DictReader(f)))


def _landmark_columns(landmarks_path: str | None) -> dict:
    if not landmarks_path:
        return {}
    with open(landmarks_path, newline="") as f:
        header = next(csv.reader(f), [])
    return {
        "image": "l{i}_{x,y,z}: x, y as fractions of frame width, height; z relative depth",
        "world": ("wl{i}_{x,y,z}: MediaPipe world landmarks, metres, hand-centred"
                  if "wl0_x" in header else None),
        "handedness": "handedness: MediaPipe Left/Right per frame" if "handedness" in header else None,
        "rows": _count_rows(landmarks_path),
    }


def _video_info(session, report: dict | None) -> dict:
    """From the extraction report; sessions extracted before it recorded the
    video are probed directly so every export carries its resolution."""
    if report and report.get("video"):
        return report["video"]
    video_path = resolve_data_path(session["video_path"])
    if not video_path:
        return {}
    from src.processing.video_io import probe_video
    info = probe_video(video_path)
    info["aspect"] = round(info["width"] / info["height"], 6) if info["height"] else None
    info["decoded_frames"] = None
    return info


def build_metadata(session, participant, report: dict | None,
                   landmarks_path: str | None, labels_path: str | None) -> dict:
    keys = session.keys()
    source_path = session["source_path"] if "source_path" in keys else None
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "participant_id": participant["participant_code"],
        "session_id": f"S{session['id']:03d}",
        "dataset": (session["dataset"] if "dataset" in keys else None) or "dataset",
        "source_file": Path(source_path).name if source_path else None,
        "lighting": session["lighting"],
        "background": session["background"],
        "dominant_hand": session["dominant_hand"],
        "date_created": session["date_created"],
        "status": session["status"],
        "notes": session["notes"] if "notes" in keys else "",
        "video": _video_info(session, report),
        "timing": (report or {}).get("timing"),
        "extraction": (report or {}).get("extraction"),
        "detection": {k: (report or {}).get(k) for k in
                      ("total_frames", "frames_with_hand", "pct_detected", "avg_confidence")},
        "landmark_columns": _landmark_columns(landmarks_path),
        "labels": {
            "set": LABELS,
            "excluded_from_training": ["unsure"],
            "unlabelled_saved_as": DEFAULT_LABEL,
            "counts": _label_counts(labels_path),
        },
    }


def export_session(session_id: int, dataset_dir: str | None = None) -> str:
    """Export a session. The output root defaults to the dataset folder the
    session was assigned on creation (dataset / dataset_<Source>)."""
    session = get_session(session_id)
    if dataset_dir is None:
        name = session["dataset"] if "dataset" in session.keys() else None
        dataset_dir = PROJECT_ROOT / (name or "dataset")
    participant = get_participant(session["participant_id"])

    p_code = participant["participant_code"]
    s_code = f"S{session_id:03d}"
    out_dir = Path(dataset_dir) / p_code / s_code
    out_dir.mkdir(parents=True, exist_ok=True)

    video_path = resolve_data_path(session["video_path"])
    if video_path:
        src_video = Path(video_path)
        shutil.copy2(src_video, out_dir / f"video{src_video.suffix}")

    landmarks_path = resolve_data_path(session["landmarks_path"])
    if landmarks_path:
        shutil.copy2(landmarks_path, out_dir / "landmarks.csv")

    labels_path = resolve_data_path(session["labels_path"])
    if labels_path:
        shutil.copy2(labels_path, out_dir / "labels.csv")

    metadata = build_metadata(session, participant, get_quality_report(session_id),
                              landmarks_path, labels_path)
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return str(out_dir)
