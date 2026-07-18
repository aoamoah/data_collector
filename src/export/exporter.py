import csv
import json
import shutil
from pathlib import Path

from src.db.models import get_session, get_participant
from src.db.paths import PROJECT_ROOT, resolve_data_path

DATASET_FOLDERS = ["dataset", "dataset_WITA", "dataset_IPN"]


def validate_export(session, total_frames: int) -> list[str]:
    """Return a list of warning strings. Empty list means export is safe to proceed."""
    warnings = []

    if not resolve_data_path(session["video_path"]):
        warnings.append("Video file is missing.")

    if not resolve_data_path(session["landmarks_path"]):
        warnings.append("Landmarks CSV is missing.")

    labels_path = resolve_data_path(session["labels_path"])
    if not labels_path:
        warnings.append("Labels CSV is missing.")
    elif total_frames > 0:
        with open(labels_path, newline="") as f:
            label_count = sum(1 for _ in csv.reader(f)) - 1  # subtract header
        if label_count < total_frames:
            warnings.append(
                f"Labels cover {label_count} frames but video has {total_frames} frames."
            )

    return warnings


def export_session(session_id: int, dataset_dir: str | None = None) -> str:
    """Export a session. The output root defaults to the dataset folder the
    session was assigned on creation (dataset / dataset_WITA / dataset_IPN)."""
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

    metadata = {
        "participant_id": p_code,
        "session_id": s_code,
        "dataset": session["dataset"] if "dataset" in session.keys() else "dataset",
        "lighting": session["lighting"],
        "background": session["background"],
        "dominant_hand": session["dominant_hand"],
        "date_created": session["date_created"],
        "status": session["status"],
        "notes": session["notes"] if "notes" in session.keys() else "",
    }
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return str(out_dir)
