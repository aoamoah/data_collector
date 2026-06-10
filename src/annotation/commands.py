from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.annotation.annotator import AnnotationStore, Annotation


class LabelCommand(ABC):
    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...


class AddAnnotationCommand(LabelCommand):
    def __init__(self, store: AnnotationStore, start: int, end: int, label: str):
        self._store = store
        self._start = start
        self._end = end
        self._label = label
        self._annotation: Annotation | None = None

    def execute(self):
        self._annotation = self._store._add(self._start, self._end, self._label)

    def undo(self):
        if self._annotation and self._annotation in self._store._annotations:
            self._store._annotations.remove(self._annotation)


class RemoveAnnotationCommand(LabelCommand):
    def __init__(self, store: AnnotationStore, annotation: Annotation):
        self._store = store
        self._annotation = annotation

    def execute(self):
        if self._annotation in self._store._annotations:
            self._store._annotations.remove(self._annotation)

    def undo(self):
        self._store._annotations.append(self._annotation)
        self._store._annotations.sort(key=lambda a: a.start_frame)


class BulkLabelCommand(LabelCommand):
    def __init__(self, store: AnnotationStore, label: str, total_frames: int):
        self._store = store
        self._label = label
        self._total_frames = total_frames
        self._added: list[Annotation] = []

    def execute(self):
        self._added = self._store._bulk_label_gaps(self._label, self._total_frames)

    def undo(self):
        for ann in self._added:
            if ann in self._store._annotations:
                self._store._annotations.remove(ann)
        self._added.clear()


class CommandHistory:
    def __init__(self):
        self._undo_stack: list[LabelCommand] = []
        self._redo_stack: list[LabelCommand] = []

    def push(self, cmd: LabelCommand):
        cmd.execute()
        self._undo_stack.append(cmd)
        self._redo_stack.clear()

    def undo(self):
        if self._undo_stack:
            cmd = self._undo_stack.pop()
            cmd.undo()
            self._redo_stack.append(cmd)

    def redo(self):
        if self._redo_stack:
            cmd = self._redo_stack.pop()
            cmd.execute()
            self._undo_stack.append(cmd)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)
