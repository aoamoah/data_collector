from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QDialogButtonBox, QComboBox, QPushButton, QMessageBox,
)

import shutil
from pathlib import Path

from src.db.models import (
    get_all_participants, get_sessions_for_participant,
    flag_session, delete_session, delete_participant, get_session,
)
from src.db.paths import resolve_data_path


def _remove_dir(path: Path):
    """Remove a directory tree, silently ignoring permission errors (e.g. OneDrive locks)."""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


class SessionBrowser(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Session")
        self.setMinimumSize(560, 400)
        self.selected_session_id: int | None = None
        self.selected_participant_id: int | None = None
        self.reprocess_requested = False

        layout = QVBoxLayout(self)

        # Participant selector + delete
        row = QHBoxLayout()
        row.addWidget(QLabel("Participant:"))
        self._participant_combo = QComboBox()
        row.addWidget(self._participant_combo, 1)
        btn_del_participant = QPushButton("Delete Participant")
        btn_del_participant.clicked.connect(self._delete_participant)
        row.addWidget(btn_del_participant)
        layout.addLayout(row)

        # Session list
        self._session_list = QListWidget()
        layout.addWidget(self._session_list)

        # Action buttons
        action_row = QHBoxLayout()
        self._btn_flag = QPushButton("Toggle Flag (Unusable)")
        self._btn_flag.clicked.connect(self._toggle_flag)
        action_row.addWidget(self._btn_flag)

        btn_del_session = QPushButton("Delete Session")
        btn_del_session.clicked.connect(self._delete_session)
        action_row.addWidget(btn_del_session)

        btn_reextract = QPushButton("Re-extract Landmarks")
        btn_reextract.clicked.connect(self._request_reprocess)
        action_row.addWidget(btn_reextract)

        btn_compare = QPushButton("Compare All Sessions…")
        btn_compare.clicked.connect(self._open_comparison)
        action_row.addWidget(btn_compare)

        btn_multi = QPushButton("Multi-Session Export…")
        btn_multi.clicked.connect(self._open_multi_export)
        action_row.addWidget(btn_multi)

        layout.addLayout(action_row)

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
            flagged = bool(s["flagged"]) if "flagged" in s.keys() else False
            flag_str = "  [FLAGGED]" if flagged else ""
            ds_name = s["dataset"] if "dataset" in s.keys() and s["dataset"] else "dataset"
            item = QListWidgetItem(
                f"Session {s['id']} — {s['date_created'][:19]}  [{s['status']}]"
                f"  ({ds_name}){flag_str}"
            )
            item.setData(256, s["id"])
            item.setData(257, p_id)
            item.setData(258, flagged)
            if flagged:
                item.setForeground(QColor("#cc4444"))
            self._session_list.addItem(item)

    def _delete_session(self):
        item = self._session_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Select a session to delete.")
            return
        session_id = item.data(256)
        session = get_session(session_id)
        reply = QMessageBox.question(
            self, "Delete Session",
            f"Delete Session {session_id} and all its annotations?\n\n"
            "Data files (video, landmarks, labels) will also be removed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Remove session data directory (best-effort)
        video_path = resolve_data_path(session["video_path"])
        if video_path:
            _remove_dir(Path(video_path).parent)

        delete_session(session_id)
        self._load_sessions()

    def _delete_participant(self):
        idx = self._participant_combo.currentIndex()
        if idx < 0:
            return
        p_id = self._participant_combo.itemData(idx)
        p_code = self._participant_combo.currentText()
        sessions = get_sessions_for_participant(p_id)
        reply = QMessageBox.question(
            self, "Delete Participant",
            f"Delete participant '{p_code}' and all {len(sessions)} of their sessions?\n\n"
            "This cannot be undone. Data files will also be removed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Remove all session data directories (best-effort)
        for s in sessions:
            video_path = resolve_data_path(s["video_path"])
            if video_path:
                _remove_dir(Path(video_path).parent)

        delete_participant(p_id)

        # Reload participant combo
        self._participants = get_all_participants()
        self._participant_combo.blockSignals(True)
        self._participant_combo.clear()
        for p in self._participants:
            self._participant_combo.addItem(p["participant_code"], p["id"])
        self._participant_combo.blockSignals(False)
        self._load_sessions()

    def _toggle_flag(self):
        item = self._session_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Select a session to flag/unflag.")
            return
        session_id = item.data(256)
        currently_flagged = bool(item.data(258))
        new_state = not currently_flagged
        flag_session(session_id, new_state)
        self._load_sessions()

    def _request_reprocess(self):
        item = self._session_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Select a session to re-extract.")
            return
        self.selected_session_id = item.data(256)
        self.selected_participant_id = item.data(257)
        self.reprocess_requested = True
        self.accept()

    def _open_comparison(self):
        from src.ui.session_comparison_dialog import SessionComparisonDialog
        dlg = SessionComparisonDialog(self)
        dlg.exec()

    def _open_multi_export(self):
        from src.ui.multi_session_export_dialog import MultiSessionExportDialog
        dlg = MultiSessionExportDialog(self)
        dlg.exec()

    def _accept(self):
        item = self._session_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Select Session", "Please select a session.")
            return
        self.selected_session_id = item.data(256)
        self.selected_participant_id = item.data(257)
        self.accept()
