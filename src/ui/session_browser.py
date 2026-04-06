from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QDialogButtonBox, QComboBox, QHBoxLayout, QMessageBox,
)
from src.db.models import get_all_participants, get_sessions_for_participant


class SessionBrowser(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Session")
        self.setMinimumSize(480, 360)
        self.selected_session_id: int | None = None
        self.selected_participant_id: int | None = None

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Participant:"))
        self._participant_combo = QComboBox()
        row.addWidget(self._participant_combo, 1)
        layout.addLayout(row)

        self._session_list = QListWidget()
        layout.addWidget(self._session_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._participants = get_all_participants()
        for p in self._participants:
            self._participant_combo.addItem(f"{p['participant_code']}", p["id"])

        self._participant_combo.currentIndexChanged.connect(self._load_sessions)
        self._load_sessions()

    def _load_sessions(self):
        self._session_list.clear()
        idx = self._participant_combo.currentIndex()
        if idx < 0:
            return
        p_id = self._participant_combo.itemData(idx)
        sessions = get_sessions_for_participant(p_id)
        for s in sessions:
            item = QListWidgetItem(
                f"Session {s['id']} — {s['date_created'][:19]}  [{s['status']}]"
            )
            item.setData(256, s["id"])
            item.setData(257, p_id)
            self._session_list.addItem(item)

    def _accept(self):
        item = self._session_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Select Session", "Please select a session.")
            return
        self.selected_session_id = item.data(256)
        self.selected_participant_id = item.data(257)
        self.accept()
