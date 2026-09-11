import csv
from dataclasses import dataclass
from pathlib import Path

from src.annotation.commands import CommandHistory, LabelCommand


# `unsure` marks frames the annotator cannot judge — motion blur, occlusion,
# a hand half out of frame. They are exported as-is and excluded from
# training and scoring rather than forced into a class, the same treatment
# the closest published benchmark gives its "uninformative" frames. Pauses
# inside a letter are `not_writing`: the thesis scores them as events
# derived from the labels, so they need no class of their own.
LABELS = ["writing", "not_writing", "unsure"]
DEFAULT_LABEL = "not_writing"


@dataclass(eq=False)
class Annotation:
    start_frame: int
    end_frame: int
    label: str
    db_id: int | None = None


class AnnotationStore:
    def __init__(self):
        self._annotations: list[Annotation] = []
        self._history = CommandHistory()

    def load(self, annotations: list):
        """Load from DB rows (sqlite3.Row objects). Resets history.

        Rows are replayed oldest-first through the same overwrite rule used
        while annotating, so any overlaps saved by older versions resolve the
        same way new ones do."""
        self._annotations = []
        for row in sorted(annotations, key=lambda r: r["id"]):
            self._annotations = self._overwritten(
                Annotation(row["start_frame"], row["end_frame"], row["label"], row["id"]))
        self._history = CommandHistory()

    # ---- command-driven mutations (tracked in history) ----

    def apply_command(self, cmd: LabelCommand):
        self._history.push(cmd)

    def undo(self):
        self._history.undo()

    def redo(self):
        self._history.redo()

    def can_undo(self) -> bool:
        return self._history.can_undo()

    def can_redo(self) -> bool:
        return self._history.can_redo()

    # ---- internal mutations used by commands ----

    def _overwritten(self, new: Annotation) -> list[Annotation]:
        """The annotation list with `new` laid over it.

        The newest annotation wins wherever it overlaps: an overlapped range
        is trimmed, or split in two when `new` falls inside it. This is what
        makes short pauses annotatable — mark the whole word as writing, then
        mark the pause inside it. Previously the older range kept priority
        and the pause was silently dropped from labels.csv.

        Untouched annotations keep their identity; trimmed pieces are new
        objects, so a snapshot of the old list stays valid for undo.
        """
        result: list[Annotation] = []
        for ann in self._annotations:
            if ann.end_frame < new.start_frame or ann.start_frame > new.end_frame:
                result.append(ann)
                continue
            if ann.start_frame < new.start_frame:
                result.append(Annotation(ann.start_frame, new.start_frame - 1, ann.label))
            if ann.end_frame > new.end_frame:
                result.append(Annotation(new.end_frame + 1, ann.end_frame, ann.label))
        result.append(new)
        result.sort(key=lambda a: a.start_frame)
        return result

    def _add(self, start_frame: int, end_frame: int, label: str) -> Annotation:
        ann = Annotation(start_frame, end_frame, label)
        self._annotations = self._overwritten(ann)
        return ann

    def _bulk_label_gaps(self, label: str, total_frames: int) -> list[Annotation]:
        """Label all uncovered frames as the given label. Returns added annotations."""
        added: list[Annotation] = []
        for start, end in self.uncovered_runs(total_frames):
            ann = Annotation(start, end, label)
            self._annotations.append(ann)
            added.append(ann)
        self._annotations.sort(key=lambda a: a.start_frame)
        return added

    # ---- direct mutations (no history — for DB-loaded data) ----

    def add(self, start_frame: int, end_frame: int, label: str) -> Annotation:
        """Direct add without command history. Used only when loading from DB."""
        return self._add(start_frame, end_frame, label)

    def remove_by_index(self, index: int) -> Annotation:
        """Direct remove without command history."""
        return self._annotations.pop(index)

    # ---- queries ----

    def get_all(self) -> list[Annotation]:
        return list(self._annotations)

    def frame_labels(self, total_frames: int) -> list[str | None]:
        """Label of every frame, None where nothing covers it."""
        labels: list[str | None] = [None] * total_frames
        for ann in self._annotations:
            for i in range(max(0, ann.start_frame), min(total_frames, ann.end_frame + 1)):
                labels[i] = ann.label
        return labels

    def uncovered_runs(self, total_frames: int) -> list[tuple[int, int]]:
        """(start, end) of every run of unlabelled frames, inclusive."""
        runs, start = [], None
        for i, label in enumerate(self.frame_labels(total_frames)):
            if label is None and start is None:
                start = i
            elif label is not None and start is not None:
                runs.append((start, i - 1))
                start = None
        if start is not None:
            runs.append((start, total_frames - 1))
        return runs

    def label_at(self, frame_index: int) -> str | None:
        """The frame's label, or None if nothing covers it."""
        for ann in self._annotations:
            if ann.start_frame <= frame_index <= ann.end_frame:
                return ann.label
        return None

    def label_for_frame(self, frame_index: int) -> str:
        return self.label_at(frame_index) or DEFAULT_LABEL

    def save_to_csv(self, path: str, total_frames: int):
        """Unlabelled frames are written as DEFAULT_LABEL — the screen warns
        about them before saving."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        labels = self.frame_labels(total_frames)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["frame_index", "label"])
            for i, label in enumerate(labels):
                writer.writerow([i, label or DEFAULT_LABEL])
