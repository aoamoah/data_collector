import re

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox,
    QTextEdit, QDialogButtonBox, QVBoxLayout, QLabel, QMessageBox,
)
from src.db.models import add_participant, get_all_participants


class ParticipantForm(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Participant")
        self.setMinimumWidth(360)
        self.participant_id: int | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Suggest one past the highest existing number — counting rows would
        # collide with surviving codes after a deletion
        existing = get_all_participants()
        nums = [
            int(m.group(1))
            for p in existing
            if (m := re.fullmatch(r"P(\d+)", p["participant_code"]))
        ]
        next_num = max(nums, default=0) + 1
        self._code = QLineEdit(f"P{next_num:03d}")
        self._handedness = QComboBox()
        self._handedness.addItems(["right", "left", "ambidextrous"])
        self._age_range = QComboBox()
        self._age_range.addItems(["18-24", "25-34", "35-44", "45-54", "55+"])
        self._notes = QTextEdit()
        self._notes.setFixedHeight(72)

        form.addRow("Participant Code", self._code)
        form.addRow("Handedness", self._handedness)
        form.addRow("Age Range", self._age_range)
        form.addRow("Notes", self._notes)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        code = self._code.text().strip()
        if not code:
            QMessageBox.warning(self, "Validation", "Participant code is required.")
            return
        try:
            self.participant_id = add_participant(
                code,
                self._handedness.currentText(),
                self._age_range.currentText(),
                self._notes.toPlainText().strip(),
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
