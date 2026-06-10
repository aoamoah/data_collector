import csv
import json
import shutil
from pathlib import Path

from src.db.models import get_session, get_participant


def validate_export(session, total_frames: int) -> list[str]:
    """Return a list of warning strings. Empty list means export is safe to proceed."""
    warnings = []

    if not session["video_path"] or not Path(session["video_path"]).exists():
        warnings.append("Video file is missing.")

    if not session["landmarks_path"] or not Path(session["landmarks_path"]).exists():
        warnings.append("Landmarks CSV is missing.")

    if not session["labels_path"] or not Path(session["labels_path"]).exists():
        warnings.append("Labels CSV is missing.")
    elif total_frames > 0:
        with open(session["labels_path"], newline="") as f:
            label_count = sum(1 for _ in csv.reader(f)) - 1  # subtract header
        if label_count < total_frames:
            warnings.append(
                f"Labels cover {label_count} frames but video has {total_frames} frames."
            )

    return warnings


def export_session(session_id: int, dataset_dir: str) -> str:
    session = get_session(session_id)
    participant = get_participant(session["participant_id"])

    p_code = participant["participant_code"]
    s_code = f"S{session_id:03d}"
    out_dir = Path(dataset_dir) / p_code / s_code
    out_dir.mkdir(parents=True, exist_ok=True)

    if session["video_path"] and Path(session["video_path"]).exists():
        shutil.copy2(session["video_path"], out_dir / "video.mp4")

    if session["landmarks_path"] and Path(session["landmarks_path"]).exists():
        shutil.copy2(session["landmarks_path"], out_dir / "landmarks.csv")

    if session["labels_path"] and Path(session["labels_path"]).exists():
        shutil.copy2(session["labels_path"], out_dir / "labels.csv")

    metadata = {
        "participant_id": p_code,
        "session_id": s_code,
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
