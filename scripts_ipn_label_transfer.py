"""Carry the July IPN labels onto the re-imported IPN sessions, corrected for
the seek misalignment.

The old annotation screen showed frame N by seeking the original .avi, and on
these FMP4 files a seek to N lands on decoded frame N - k(N). So the label
given to "frame N" belongs to decoded frame m(N). Here every N is seeked with
the same OpenCV and matched by exact pixel hash to the sequentially decoded
frames (the numbering the new extraction and proxy use). The old label runs
are moved frame by frame: decoded frame m(N) takes old[N]. Where a shift jump
showed a frame twice, the later viewing wins; a frame never shown takes the
label of the frame before it.

Only sessions in dataset_IPN with status 'processed' and no annotations are
touched, so nothing annotated by hand is overwritten.

    venv/bin/python scripts_ipn_label_transfer.py --dry-run   # report only
    venv/bin/python scripts_ipn_label_transfer.py
"""
import argparse
import csv
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))

OLD_ROOT = Path.home() / "airwrite_trainer" / "dataset_IPN"
DATA_DIR = Path(__file__).parent / "data"
REPORT = Path.home() / "ipn_label_transfer_report.csv"


def _hash(frame) -> str:
    return hashlib.md5(frame.tobytes()).hexdigest()


def seek_map(video: str) -> dict:
    """m[N] = decoded index of the frame a seek to N shows, for every header N."""
    cap = cv2.VideoCapture(video)
    where: dict[str, list[int]] = {}
    n_decoded = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        where.setdefault(_hash(frame), []).append(n_decoded)
        n_decoded += 1
    header = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    cap = cv2.VideoCapture(video)
    m: list[int | None] = []
    for n in range(header):
        cap.set(cv2.CAP_PROP_POS_FRAMES, n)
        ok, frame = cap.read()
        hits = where.get(_hash(frame)) if ok else None
        # identical frames are possible in principle; the one nearest N wins
        m.append(min(hits, key=lambda i: abs(i - n)) if hits else None)
    cap.release()

    # a failed seek takes the offset of the nearest resolved neighbour
    # seeks past the last decoded frame fail on some files; that is expected
    unresolved = sum(x is None for x in m[:n_decoded])
    last_k = 0
    for n in range(header):
        if m[n] is None:
            m[n] = max(0, min(n_decoded - 1, n - last_k))
        else:
            last_k = n - m[n]
    ks = [n - x for n, x in enumerate(m)]
    return {"m": m, "decoded": n_decoded, "header": header,
            "unresolved": unresolved, "max_k": max(ks, default=0),
            "min_k": min(ks, default=0),
            "monotone": all(a <= b for a, b in zip(m, m[1:]))}


def runs_of(labels: list[str]) -> list[tuple[int, int, str]]:
    runs, start = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            runs.append((start, i - 1, labels[start]))
            start = i
    return runs


def old_sessions() -> dict[str, Path]:
    """Original IPN file name -> old export session folder."""
    out = {}
    for meta in OLD_ROOT.glob("P*/S*/metadata.json"):
        notes = json.loads(meta.read_text()).get("notes", "")
        if notes.startswith("bulk import: "):
            out[notes[len("bulk import: "):]] = meta.parent
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    from src.db.database import init_db, get_connection
    from src.db.models import (
        get_annotations_for_session, add_annotation, update_session,
    )
    from src.annotation.annotator import AnnotationStore

    init_db()
    olds = old_sessions()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT s.id, s.status, s.source_path, s.video_path, s.landmarks_path,
                      s.notes, p.participant_code
               FROM sessions s JOIN participants p ON p.id = s.participant_id
               WHERE s.dataset = 'dataset_IPN' ORDER BY s.id""").fetchall()

    jobs, skipped = [], []
    for r in rows:
        name = Path(r["source_path"] or "").name
        if r["status"] != "processed":
            skipped.append(f"S{r['id']:03d} {name}: status {r['status']}")
        elif get_annotations_for_session(r["id"]):
            skipped.append(f"S{r['id']:03d} {name}: already has annotations")
        elif name not in olds:
            skipped.append(f"S{r['id']:03d} {name}: no old export found")
        else:
            jobs.append((r, olds[name]))
    print(f"{len(jobs)} session(s) to transfer, {len(skipped)} skipped", flush=True)
    for s in skipped:
        print("  skip " + s)

    with ProcessPoolExecutor(args.workers) as pool:
        maps = pool.map(seek_map, [r["video_path"] for r, _ in jobs])
        report = []
        for (r, old_dir), mp in zip(jobs, maps):
            tag = f"S{r['id']:03d} {r['participant_code']} {Path(r['source_path']).name}"
            with open(r["landmarks_path"]) as f:
                total = sum(1 for _ in f) - 1
            with open(old_dir / "labels.csv", newline="") as f:
                old = [row["label"] for row in csv.DictReader(f)]

            problems = []
            if total != mp["decoded"]:
                problems.append(f"landmarks {total} != decoded {mp['decoded']}")
            if len(old) != mp["header"]:
                problems.append(f"old labels {len(old)} != header {mp['header']}")
            if mp["unresolved"]:
                problems.append(f"{mp['unresolved']} seeks unmatched")

            m = mp["m"]
            new: list[str | None] = [None] * total
            for n, label in enumerate(old[:len(m)]):
                if 0 <= m[n] < total:
                    new[m[n]] = label
            gaps = sum(x is None for x in new)
            for i in range(total):
                if new[i] is None:
                    new[i] = new[i - 1] if i else next(x for x in new if x)
            store = AnnotationStore()
            for s, e, label in runs_of(new):
                store.add(s, e, label)
            moved = sum(1 for i, x in enumerate(new)
                        if i < len(old) and x != old[i])

            row = {
                "session": f"S{r['id']:03d}", "participant": r["participant_code"],
                "file": Path(r["source_path"]).name, "old_dir": str(old_dir.relative_to(OLD_ROOT)),
                "header": mp["header"], "decoded": mp["decoded"], "max_shift": mp["max_k"],
                "old_writing": old.count("writing"), "new_writing": new.count("writing"),
                "frames_relabelled": moved, "frames_never_shown": gaps, "annotations": len(store.get_all()),
                "problems": "; ".join(problems),
            }
            report.append(row)
            print(f"{tag}: shift up to {mp['max_k']}, {moved} frame(s) relabelled"
                  + (f"  PROBLEM: {row['problems']}" if problems else ""), flush=True)

            if args.dry_run or problems:
                continue
            for ann in store.get_all():
                add_annotation(r["id"], ann.start_frame, ann.end_frame, ann.label)
            labels_path = DATA_DIR / r["participant_code"] / f"S{r['id']:03d}" / "labels.csv"
            store.save_to_csv(str(labels_path), total)
            note = (f"labels transferred from old export {row['old_dir']}, "
                    f"seek shift up to {mp['max_k']} corrected")
            update_session(r["id"], labels_path=str(labels_path), status="annotated",
                           notes=f"{r['notes']}; {note}" if r["notes"] else note)

    if report:
        with open(REPORT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(report[0]))
            w.writeheader()
            w.writerows(report)
    bad = [r for r in report if r["problems"]]
    print(f"\n{'DRY RUN: ' if args.dry_run else ''}{len(report) - len(bad)} transferred"
          f"{'' if args.dry_run else ''}, {len(bad)} held back with problems. Report: {REPORT}")


if __name__ == "__main__":
    main()
