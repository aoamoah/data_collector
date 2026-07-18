import csv
import random
from pathlib import Path

from src.db.models import get_session, get_participant
from src.db.paths import resolve_data_path


def export_multi_session(
    session_ids: list[int],
    output_dir: str,
    split_ratios: tuple[float, float, float] | None = None,
) -> dict:
    """
    Export multiple sessions into a combined CSV.
    If split_ratios is provided (train, val, test), sessions are split at the session
    level (whole sessions go to one split) and output into separate subdirectories.
    Returns a result dict with keys: success, warnings, output_path.
    """
    sessions = [get_session(sid) for sid in session_ids]
    sessions = [s for s in sessions if s is not None]
    out = Path(output_dir)

    if split_ratios:
        return _export_with_split(sessions, out, split_ratios)
    return _export_combined(sessions, out / "combined")


def _load_session_rows(session) -> list[dict]:
    landmarks_path = resolve_data_path(session["landmarks_path"])
    labels_path = resolve_data_path(session["labels_path"])
    if not landmarks_path or not labels_path:
        return []

    participant = get_participant(session["participant_id"])
    p_code = participant["participant_code"]
    s_code = f"S{session['id']:03d}"

    with open(labels_path, newline="") as ll:
        labels_by_frame = {
            int(row["frame_index"]): row["label"]
            for row in csv.DictReader(ll)
        }

    rows = []
    with open(landmarks_path, newline="") as lf:
        for row in csv.DictReader(lf):
            fi = int(row["frame_index"])
            row["participant_id"] = p_code
            row["session_id"] = s_code
            row["label"] = labels_by_frame.get(fi, "not_writing")
            rows.append(row)
    return rows


def _export_combined(sessions: list, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    warnings = []

    for session in sessions:
        rows = _load_session_rows(session)
        if not rows:
            warnings.append(
                f"Session {session['id']}: landmarks or labels missing — skipped."
            )
        else:
            all_rows.extend(rows)

    if not all_rows:
        return {
            "success": False,
            "warnings": warnings or ["No valid sessions to export."],
            "output_path": str(out_dir),
        }

    out_csv = out_dir / "combined.csv"
    # Put participant_id, session_id, label first for readability
    fixed = ["participant_id", "session_id", "label"]
    rest = [k for k in all_rows[0].keys() if k not in fixed]
    fieldnames = fixed + rest

    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    return {"success": True, "warnings": warnings, "output_path": str(out_csv)}


def _export_with_split(
    sessions: list, out_dir: Path, ratios: tuple[float, float, float]
) -> dict:
    train_r, val_r, _ = ratios
    shuffled = list(sessions)
    random.seed(42)
    random.shuffle(shuffled)

    n = len(shuffled)
    n_train = round(n * train_r)
    n_val = round(n * val_r)

    splits = {
        "train": shuffled[:n_train],
        "val": shuffled[n_train : n_train + n_val],
        "test": shuffled[n_train + n_val :],
    }

    all_warnings: list[str] = []
    for split_name, split_sessions in splits.items():
        if not split_sessions:
            all_warnings.append(f"Split '{split_name}' is empty (too few sessions).")
            continue
        result = _export_combined(split_sessions, out_dir / split_name)
        all_warnings.extend(result["warnings"])

    return {"success": True, "warnings": all_warnings, "output_path": str(out_dir)}
