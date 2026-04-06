from PySide6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QDialogButtonBox, QVBoxLayout, QLabel,
)
from src.db.models import add_session


class SessionForm(QDialog):
    def __init__(self, participant_id: int, participant_code: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Session")
        self.setMinimumWidth(320)
        self.session_id: int | None = None
        self._participant_id = participant_id

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Participant: <b>{participant_code}</b>"))

        form = QFormLayout()
        self._lighting = QComboBox()
        self._lighting.addItems(["bright", "normal", "dim"])
        self._background = QComboBox()
        self._background.addItems(["plain", "cluttered", "outdoor"])
        self._dominant_hand = QComboBox()
        self._dominant_hand.addItems(["right", "left"])

        form.addRow("Lighting", self._lighting)
        form.addRow("Background", self._background)
        form.addRow("Dominant Hand", self._dominant_hand)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self.session_id = add_session(
            self._participant_id,
            self._lighting.currentText(),
            self._background.currentText(),
            self._dominant_hand.currentText(),
        )
        self.accept()
