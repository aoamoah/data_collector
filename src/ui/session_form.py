from PySide6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QDialogButtonBox,
    QVBoxLayout, QLabel, QTextEdit, QPushButton,
)

from src.config import AppConfig, DEFAULT_TASK_DURATIONS
from src.db.models import add_session
from src.ui.task_duration_editor import TaskDurationEditor


class SessionForm(QDialog):
    def __init__(self, participant_id: int, participant_code: str, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Session")
        self.setMinimumWidth(360)
        self.session_id: int | None = None
        self._participant_id = participant_id
        self._config = config
        self._task_durations = list(config.task_durations)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Participant: <b>{participant_code}</b>"))

        form = QFormLayout()
        self._dataset = QComboBox()
        self._dataset.addItems(["dataset", "dataset_WITA", "dataset_IPN"])
        self._dataset.setToolTip(
            "Which collection this session belongs to — determines the folder "
            "the exported files go into."
        )
        self._lighting = QComboBox()
        self._lighting.addItems(["bright", "normal", "dim"])
        self._background = QComboBox()
        self._background.addItems(["plain", "cluttered", "outdoor"])
        self._dominant_hand = QComboBox()
        self._dominant_hand.addItems(["right", "left"])

        form.addRow("Dataset", self._dataset)
        form.addRow("Lighting", self._lighting)
        form.addRow("Background", self._background)
        form.addRow("Dominant Hand", self._dominant_hand)
        layout.addLayout(form)

        layout.addWidget(QLabel("Session notes (optional):"))
        self._notes = QTextEdit()
        self._notes.setMaximumHeight(80)
        self._notes.setPlaceholderText("Any notes about this session…")
        layout.addWidget(self._notes)

        btn_durations = QPushButton("Configure Task Durations…")
        btn_durations.clicked.connect(self._edit_durations)
        layout.addWidget(btn_durations)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _edit_durations(self):
        dlg = TaskDurationEditor(self._task_durations, self)
        if dlg.exec():
            self._task_durations = dlg.get_durations()
            self._config.task_durations = self._task_durations

    def _save(self):
        self.session_id = add_session(
            self._participant_id,
            self._lighting.currentText(),
            self._background.currentText(),
            self._dominant_hand.currentText(),
            notes=self._notes.toPlainText().strip(),
            dataset=self._dataset.currentText(),
        )
        self.accept()
