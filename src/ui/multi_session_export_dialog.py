from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QCheckBox, QGroupBox, QDoubleSpinBox, QFormLayout,
    QPushButton, QDialogButtonBox, QFileDialog, QLineEdit, QMessageBox,
)

from src.db.models import get_all_sessions
from src.export.multi_exporter import export_multi_session

DATASET_DIR = Path(__file__).parent.parent.parent / "dataset"


class MultiSessionExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Multi-Session Export")
        self.setMinimumSize(600, 480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Select sessions to export:</b>"))

        self._session_list = QListWidget()
        self._session_list.setSelectionMode(QListWidget.MultiSelection)
        self._sessions = get_all_sessions()
        for s in self._sessions:
            flagged = bool(s["flagged"]) if "flagged" in s.keys() else False
            flag_str = " [FLAGGED]" if flagged else ""
            item = QListWidgetItem(
                f"{s['participant_code']}  S{s['id']:03d}  {s['date_created'][:10]}"
                f"  [{s['status']}]{flag_str}"
            )
            item.setData(Qt.UserRole, s["id"])
            if flagged:
                item.setForeground(Qt.red)
            self._session_list.addItem(item)
        layout.addWidget(self._session_list)

        # Split options
        split_box = QGroupBox("Train / Val / Test Split (optional)")
        split_box.setCheckable(True)
        split_box.setChecked(False)
        self._split_group = split_box
        split_form = QFormLayout(split_box)

        self._train_spin = QDoubleSpinBox()
        self._val_spin = QDoubleSpinBox()
        self._test_spin = QDoubleSpinBox()
        for spin in (self._train_spin, self._val_spin, self._test_spin):
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
        self._train_spin.setValue(0.70)
        self._val_spin.setValue(0.15)
        self._test_spin.setValue(0.15)
        split_form.addRow("Train ratio", self._train_spin)
        split_form.addRow("Val ratio", self._val_spin)
        split_form.addRow("Test ratio", self._test_spin)
        layout.addWidget(split_box)

        # Output directory
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output directory:"))
        self._out_edit = QLineEdit(str(DATASET_DIR / "multi_export"))
        out_row.addWidget(self._out_edit, 1)
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse)
        out_row.addWidget(btn_browse)
        layout.addLayout(out_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        export_btn = QPushButton("Export")
        export_btn.setDefault(True)
        export_btn.clicked.connect(self._export)
        buttons.addButton(export_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory", self._out_edit.text())
        if d:
            self._out_edit.setText(d)

    def _export(self):
        selected_ids = [
            item.data(Qt.UserRole)
            for item in self._session_list.selectedItems()
        ]
        if not selected_ids:
            QMessageBox.warning(self, "No Sessions", "Select at least one session.")
            return

        split_ratios = None
        if self._split_group.isChecked():
            t, v, te = self._train_spin.value(), self._val_spin.value(), self._test_spin.value()
            total = t + v + te
            if abs(total - 1.0) > 0.01:
                QMessageBox.warning(self, "Invalid Ratios", f"Ratios must sum to 1.0 (currently {total:.2f}).")
                return
            split_ratios = (t, v, te)

        result = export_multi_session(selected_ids, self._out_edit.text(), split_ratios)

        msg = f"Export complete.\nOutput: {result['output_path']}"
        if result["warnings"]:
            msg += "\n\nWarnings:\n" + "\n".join(f"• {w}" for w in result["warnings"])
        QMessageBox.information(self, "Export Complete", msg)
        self.accept()
