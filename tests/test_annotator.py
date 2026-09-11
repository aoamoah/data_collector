import csv

from src.annotation.annotator import AnnotationStore
from src.annotation.commands import AddAnnotationCommand, BulkLabelCommand, RemoveAnnotationCommand


def spans(store):
    return [(a.start_frame, a.end_frame, a.label) for a in store.get_all()]


def test_pause_inside_writing_splits_the_range():
    store = AnnotationStore()
    store.apply_command(AddAnnotationCommand(store, 0, 99, "writing"))
    store.apply_command(AddAnnotationCommand(store, 40, 44, "not_writing"))
    assert spans(store) == [(0, 39, "writing"), (40, 44, "not_writing"), (45, 99, "writing")]
    labels = store.frame_labels(100)
    assert labels[39] == "writing" and labels[40] == "not_writing" and labels[45] == "writing"


def test_newest_annotation_wins_partial_overlap():
    store = AnnotationStore()
    store.apply_command(AddAnnotationCommand(store, 10, 30, "writing"))
    store.apply_command(AddAnnotationCommand(store, 25, 50, "unsure"))
    assert spans(store) == [(10, 24, "writing"), (25, 50, "unsure")]


def test_undo_restores_the_split_range_and_redo_reapplies():
    store = AnnotationStore()
    store.apply_command(AddAnnotationCommand(store, 0, 99, "writing"))
    store.apply_command(AddAnnotationCommand(store, 40, 44, "not_writing"))
    store.undo()
    assert spans(store) == [(0, 99, "writing")]
    store.redo()
    assert spans(store) == [(0, 39, "writing"), (40, 44, "not_writing"), (45, 99, "writing")]
    store.undo()
    store.undo()
    assert spans(store) == []


def test_remove_then_undo_round_trips():
    store = AnnotationStore()
    store.apply_command(AddAnnotationCommand(store, 0, 9, "writing"))
    store.apply_command(AddAnnotationCommand(store, 20, 29, "writing"))
    target = store.get_all()[1]
    store.apply_command(RemoveAnnotationCommand(store, target))
    assert spans(store) == [(0, 9, "writing")]
    store.undo()
    assert spans(store) == [(0, 9, "writing"), (20, 29, "writing")]


def test_fill_gaps_labels_only_uncovered_frames():
    store = AnnotationStore()
    store.apply_command(AddAnnotationCommand(store, 5, 9, "writing"))
    assert store.uncovered_runs(15) == [(0, 4), (10, 14)]
    store.apply_command(BulkLabelCommand(store, "not_writing", 15))
    assert store.uncovered_runs(15) == []
    store.undo()
    assert store.uncovered_runs(15) == [(0, 4), (10, 14)]


def test_load_replays_saved_overlaps_oldest_first():
    rows = [
        {"id": 1, "start_frame": 0, "end_frame": 99, "label": "writing"},
        {"id": 2, "start_frame": 40, "end_frame": 44, "label": "not_writing"},
    ]
    store = AnnotationStore()
    store.load(rows)
    assert store.frame_labels(100)[42] == "not_writing"
    assert not store.can_undo()


def test_save_to_csv_writes_every_frame(tmp_path):
    store = AnnotationStore()
    store.apply_command(AddAnnotationCommand(store, 2, 3, "writing"))
    store.apply_command(AddAnnotationCommand(store, 4, 4, "unsure"))
    out = tmp_path / "labels.csv"
    store.save_to_csv(str(out), 6)
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["label"] for r in rows] == [
        "not_writing", "not_writing", "writing", "writing", "unsure", "not_writing"]
    assert [int(r["frame_index"]) for r in rows] == list(range(6))
