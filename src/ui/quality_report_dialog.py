from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHeaderView,
)
from PySide6.QtCore import Qt


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
