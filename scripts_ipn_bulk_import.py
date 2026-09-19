"""Headless Bulk Import of ~/ipn_videos/<P###_IPN>/*.avi into dataset_IPN.

Does what BulkImportDialog does for each video (session row, copy the video
in, extract landmarks + annotation proxy, save the quality report), one video
at a time. Safe to re-run: a video already imported (same source_path) with
status 'processed' or later is skipped; one left half-done is retried.

    venv/bin/python scripts_ipn_bulk_import.py
"""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import AppConfig
from src.db.database import init_db, get_connection
from src.db.models import (
    get_all_participants, add_session, update_session, save_quality_report,
)
from src.processing.extractor import extract_landmarks
from src.processing.video_io import proxy_path_for

SRC_ROOT = Path.home() / "ipn_videos"
DATA_DIR = Path(__file__).parent / "data"
DATASET = "dataset_IPN"
HAND = "right"


def main():
    init_db()
    config = AppConfig()
    participants = {p["participant_code"]: p["id"] for p in get_all_participants()}
    with get_connection() as conn:
        existing = {r["source_path"]: (r["id"], r["status"]) for r in conn.execute(
            "SELECT id, source_path, status FROM sessions WHERE dataset = ?", (DATASET,))}

    jobs = sorted(SRC_ROOT.glob("*/*.avi"))
    print(f"{len(jobs)} videos found under {SRC_ROOT}", flush=True)
    errors = []
    t0 = time.time()
    for n, video in enumerate(jobs, 1):
        code = video.parent.name
        tag = f"[{n}/{len(jobs)}] {code}/{video.name}"
        if code not in participants:
            errors.append(f"{tag}: participant {code} not in DB")
            print(f"{tag}: SKIP, participant missing", flush=True)
            continue
        prior = existing.get(str(video))
        if prior and prior[1] in ("processed", "annotated", "exported"):
            print(f"{tag}: already imported as S{prior[0]:03d}, skipped", flush=True)
            continue

        if prior:
            session_id = prior[0]   # a previous run stopped part-way; redo it
        else:
            session_id = add_session(
                participants[code], lighting="normal", background="plain",
                dominant_hand=HAND, notes=f"bulk import: {video.name}",
                dataset=DATASET, source_path=str(video))
        out_dir = DATA_DIR / code / f"S{session_id:03d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"video{video.suffix.lower()}"
        shutil.copy2(video, dest)
        update_session(session_id, status="recorded", video_path=str(dest))

        out_csv = out_dir / "landmarks.csv"
        start = time.time()
        try:
            report = extract_landmarks(
                str(dest), str(out_csv),
                confidence_threshold=config.confidence_threshold,
                target_hand=HAND,
                proxy_path=str(proxy_path_for(str(out_csv))))
        except Exception as exc:
            errors.append(f"{tag} (S{session_id:03d}): {exc}")
            print(f"{tag}: ERROR {exc}", flush=True)
            continue
        save_quality_report(session_id, report)
        update_session(session_id, landmarks_path=str(out_csv), status="processed")
        print(f"{tag}: S{session_id:03d} done in {time.time() - start:.0f}s "
              f"({(time.time() - t0) / 60:.1f} min total)", flush=True)

    print(f"\nFinished in {(time.time() - t0) / 60:.1f} min, {len(errors)} error(s)")
    for e in errors:
        print("  " + e)


if __name__ == "__main__":
    main()
