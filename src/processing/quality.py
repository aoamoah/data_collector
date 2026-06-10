from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHeaderView,
)
from PySide6.QtCore import Qt


@dataclass
class FrameQuality:
    frame_index: int
    timestamp_ms: int
    confidence: float
    hand_detected: bool
    is_duplicate: bool = False


def compute_quality_report(frame_qualities: list[FrameQuality]) -> dict:
    if not frame_qualities:
        return {}
    total = len(frame_qualities)
    duplicates = sum(1 for f in frame_qualities if f.is_duplicate)
    valid = [f for f in frame_qualities if not f.is_duplicate]
    with_hand = sum(1 for f in valid if f.hand_detected)
    confidences = [f.confidence for f in valid if f.hand_detected]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "total_frames": total,
        "frames_with_hand": with_hand,
        "pct_detected": round(100 * with_hand / total, 1) if total > 0 else 0.0,
        "avg_confidence": round(avg_conf, 4),
        "duplicate_frames": duplicates,
    }


class QualityReportDialog(QDialog):
    def __init__(self, report: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Extraction Quality Report")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        title = QLabel("<b>Hand Landmark Extraction Complete</b>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        pct = report.get("pct_detected", 0)
        if pct >= 80:
            quality_label = f"<font color='green'>Good ({pct}% frames detected)</font>"
        elif pct >= 50:
            quality_label = f"<font color='orange'>Fair ({pct}% frames detected)</font>"
        else:
            quality_label = f"<font color='red'>Poor ({pct}% frames detected)</font>"

        lbl = QLabel(quality_label)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 14px;")
        layout.addWidget(lbl)

        rows = [
            ("Total frames", str(report.get("total_frames", 0))),
            ("Frames with hand detected", str(report.get("frames_with_hand", 0))),
            ("Detection rate", f"{pct}%"),
            ("Avg confidence (detected frames)", f"{report.get('avg_confidence', 0):.4f}"),
            ("Duplicate / corrupted frames", str(report.get("duplicate_frames", 0))),
        ]

        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setFixedHeight(180)
        for i, (metric, value) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(metric))
            table.setItem(i, 1, QTableWidgetItem(value))
        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
