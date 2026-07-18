import csv
from dataclasses import dataclass
from pathlib import Path

from src.annotation.commands import CommandHistory, LabelCommand


LABELS = ["writing", "not_writing"]


@dataclass
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
        """Load from DB rows (sqlite3.Row objects). Resets history."""
        self._annotations = [
            Annotation(
                start_frame=row["start_frame"],
                end_frame=row["end_frame"],
                label=row["label"],
                db_id=row["id"],
            )
            for row in annotations
        ]
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

    def _add(self, start_frame: int, end_frame: int, label: str) -> Annotation:
        ann = Annotation(start_frame, end_frame, label)
        self._annotations.append(ann)
        self._annotations.sort(key=lambda a: a.start_frame)
        return ann

    def _bulk_label_gaps(self, label: str, total_frames: int) -> list[Annotation]:
        """Label all uncovered frames as the given label. Returns added annotations."""
        covered: set[int] = set()
        for ann in self._annotations:
            covered.update(range(ann.start_frame, ann.end_frame + 1))

        uncovered = [f for f in range(total_frames) if f not in covered]
        if not uncovered:
            return []

        added: list[Annotation] = []
        start = prev = uncovered[0]
        for f in uncovered[1:]:
            if f != prev + 1:
                added.append(self._add(start, prev, label))
                start = f
            prev = f
        added.append(self._add(start, prev, label))
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

    def label_for_frame(self, frame_index: int) -> str:
        for ann in self._annotations:
            if ann.start_frame <= frame_index <= ann.end_frame:
                return ann.label
        return "not_writing"

    def save_to_csv(self, path: str, total_frames: int):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["frame_index", "label"])
            for i in range(total_frames):
                writer.writerow([i, self.label_for_frame(i)])
