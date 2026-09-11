"""A strip under the video showing every frame's label.

Short pauses inside a letter are a few frames long; in a list of ranges they
are invisible, on a strip they are a visible notch. Clicking or dragging
seeks.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

LABEL_COLORS = {
    "writing": QColor("#2e9d5b"),
    "not_writing": QColor("#5b6b7f"),
    "unsure": QColor("#e0a030"),
    None: QColor("#2a2a2a"),        # unlabelled
}


class LabelTimeline(QWidget):
    seek_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._runs: list[tuple[int, int, str | None]] = []
        self._total = 0
        self._position = 0
        self._marks: tuple[int | None, int | None] = (None, None)
        self.setMinimumHeight(22)
        self.setMaximumHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Green: writing · Grey: not_writing · Amber: unsure · "
                        "Dark: unlabelled. Click or drag to seek.")

    def set_labels(self, labels: list[str | None]):
        self._total = len(labels)
        self._runs = []
        start = 0
        for i in range(1, self._total + 1):
            if i == self._total or labels[i] != labels[start]:
                self._runs.append((start, i - 1, labels[start]))
                start = i
        self.update()

    def set_position(self, frame: int):
        self._position = frame
        self.update()

    def set_marks(self, start: int | None, end: int | None):
        self._marks = (start, end)
        self.update()

    def _x(self, frame: float) -> float:
        return frame * self.width() / max(1, self._total)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), LABEL_COLORS[None])
        h = self.height()
        for start, end, label in self._runs:
            x0, x1 = self._x(start), self._x(end + 1)
            # Keep one-frame runs visible even on a long session
            p.fillRect(int(x0), 0, max(1, int(round(x1 - x0))), h,
                       LABEL_COLORS.get(label, LABEL_COLORS[None]))
        mark_start, mark_end = self._marks
        if mark_start is not None:
            x_end = self._x((mark_end if mark_end is not None else self._position) + 1)
            x0 = self._x(mark_start)
            p.fillRect(int(x0), 0, max(1, int(x_end - x0)), 4, QColor("#4da3ff"))
        if self._total:
            p.setPen(QPen(QColor("white"), 2))
            x = int(self._x(self._position + 0.5))
            p.drawLine(x, 0, x, h)
        p.end()

    def _seek_to(self, x: float):
        if self._total:
            frame = int(x * self._total / max(1, self.width()))
            self.seek_requested.emit(max(0, min(self._total - 1, frame)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._seek_to(event.position().x())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._seek_to(event.position().x())
