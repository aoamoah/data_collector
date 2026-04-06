import csv
from dataclasses import dataclass, field
from pathlib import Path


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

    def load(self, annotations: list):
        """Load from DB rows (sqlite3.Row objects)."""
        self._annotations = [
            Annotation(
                start_frame=row["start_frame"],
                end_frame=row["end_frame"],
                label=row["label"],
                db_id=row["id"],
            )
            for row in annotations
        ]

    def add(self, start_frame: int, end_frame: int, label: str) -> Annotation:
        ann = Annotation(start_frame, end_frame, label)
        self._annotations.append(ann)
        self._annotations.sort(key=lambda a: a.start_frame)
        return ann

    def remove_by_index(self, index: int) -> Annotation:
        return self._annotations.pop(index)

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
