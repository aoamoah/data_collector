import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHeaderView,
)

from src.db.models import get_all_sessions


class SessionComparisonDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Comparison")
        self.setMinimumSize(900, 400)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>All Sessions — Quality Comparison</b>"))

        columns = [
            "Participant", "Session", "Date", "Lighting",
            "Background", "Hand", "Status", "% Detected", "Avg Conf.", "Flagged",
        ]
        sessions = get_all_sessions()

        self._table = QTableWidget(len(sessions), len(columns))
        self._table.setHorizontalHeaderLabels(columns)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        for col in range(len(columns)):
            self._table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        for row, s in enumerate(sessions):
            report = {}
            if s["quality_report"]:
                try:
                    report = json.loads(s["quality_report"])
                except Exception:
                    pass

            pct = report.get("pct_detected", "—")
            avg_conf = report.get("avg_confidence", "—")
            flagged = bool(s["flagged"]) if "flagged" in s.keys() else False

            values = [
                s["participant_code"],
                f"S{s['id']:03d}",
                s["date_created"][:10],
                s["lighting"] or "—",
                s["background"] or "—",
                s["dominant_hand"] or "—",
                s["status"] or "—",
                f"{pct}%" if isinstance(pct, (int, float)) else pct,
                f"{avg_conf:.4f}" if isinstance(avg_conf, float) else avg_conf,
                "Yes" if flagged else "No",
            ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                if flagged:
                    item.setForeground(QColor("#cc4444"))
                elif isinstance(pct, (int, float)) and pct < 50 and col == 7:
                    item.setForeground(QColor("#cc8800"))
                self._table.setItem(row, col, item)

        layout.addWidget(self._table)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
