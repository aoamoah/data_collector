from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QPushButton, QLabel, QMessageBox,
)

from src.db.models import get_all_participants, get_session
from src.ui.participant_form import ParticipantForm
from src.ui.session_form import SessionForm
from src.ui.session_browser import SessionBrowser
from src.ui.recording_screen import RecordingScreen
from src.ui.processing_screen import ProcessingScreen
from src.ui.annotation_screen import AnnotationScreen


PAGE_HOME = 0
PAGE_RECORDING = 1
PAGE_PROCESSING = 2
PAGE_ANNOTATION = 3


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AirWrite Capture")
        self.setMinimumSize(900, 650)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._home = self._build_home()
        self._recording = RecordingScreen(self)
        self._processing = ProcessingScreen(self)
        self._annotation = AnnotationScreen(self)

        self._stack.addWidget(self._home)       # 0
        self._stack.addWidget(self._recording)  # 1
        self._stack.addWidget(self._processing) # 2
        self._stack.addWidget(self._annotation) # 3

        self._recording.recording_done.connect(self._go_to_processing)
        self._processing.processing_done.connect(self._go_to_annotation)
        self._annotation.done.connect(self.show_home)

        self._stack.setCurrentIndex(PAGE_HOME)

    # ---------- Home screen ----------

    def _build_home(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        title = QLabel("AirWrite Capture")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("Air-Writing Data Collection")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: gray;")
        layout.addWidget(subtitle)

        layout.addSpacing(32)

        for label, slot in [
            ("New Participant", self._on_new_participant),
            ("New Session", self._on_new_session),
            ("Open Session", self._on_open_session),
        ]:
            btn = QPushButton(label)
            btn.setFixedWidth(220)
            btn.setFixedHeight(44)
            btn.clicked.connect(slot)
            layout.addWidget(btn, alignment=Qt.AlignCenter)

        return widget

    # ---------- Navigation ----------

    def show_home(self):
        self._stack.setCurrentIndex(PAGE_HOME)

    def _go_to_processing(self, session_id: int):
        self._processing.load_session(session_id)
        self._stack.setCurrentIndex(PAGE_PROCESSING)

    def _go_to_annotation(self, session_id: int):
        self._annotation.load_session(session_id)
        self._stack.setCurrentIndex(PAGE_ANNOTATION)

    # ---------- Button handlers ----------

    def _on_new_participant(self):
        dlg = ParticipantForm(self)
        if dlg.exec():
            QMessageBox.information(
                self, "Created",
                f"Participant created (ID {dlg.participant_id}).\nNow create a session.",
            )

    def _on_new_session(self):
        participants = get_all_participants()
        if not participants:
            QMessageBox.warning(self, "No Participants", "Create a participant first.")
            return

        # Let user pick participant inline via SessionBrowser-style combo in SessionForm.
        # For simplicity: use the most-recently-added participant by default but let them
        # choose via session browser.
        browser = _ParticipantPicker(participants, self)
        if not browser.exec():
            return
        p = browser.selected

        dlg = SessionForm(p["id"], p["participant_code"], self)
        if dlg.exec() and dlg.session_id:
            self._recording.load_session(dlg.session_id)
            self._stack.setCurrentIndex(PAGE_RECORDING)

    def _on_open_session(self):
        dlg = SessionBrowser(self)
        if dlg.exec() and dlg.selected_session_id:
            session_id = dlg.selected_session_id
            session = get_session(session_id)
            status = session["status"]

            if status in ("created", "recording", "recorded"):
                self._recording.load_session(session_id)
                self._stack.setCurrentIndex(PAGE_RECORDING)
            elif status == "processed":
                self._annotation.load_session(session_id)
                self._stack.setCurrentIndex(PAGE_ANNOTATION)
            elif status in ("annotated", "exported"):
                self._annotation.load_session(session_id)
                self._stack.setCurrentIndex(PAGE_ANNOTATION)
            else:
                self._recording.load_session(session_id)
                self._stack.setCurrentIndex(PAGE_RECORDING)

    def closeEvent(self, event):
        self._recording.cleanup()
        self._annotation.cleanup()
        super().closeEvent(event)


# ---- small helper dialog for participant selection ----

from PySide6.QtWidgets import QDialog, QComboBox, QDialogButtonBox


class _ParticipantPicker(QDialog):
    def __init__(self, participants, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Participant")
        self.setMinimumWidth(300)
        self.selected = None
        self._participants = participants

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select participant for this session:"))
        self._combo = QComboBox()
        for p in participants:
            self._combo.addItem(p["participant_code"], p["id"])
        layout.addWidget(self._combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._pick)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick(self):
        idx = self._combo.currentIndex()
        self.selected = self._participants[idx]
        self.accept()
