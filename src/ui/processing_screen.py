from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton, QMessageBox,
)

from src.processing.extractor import ExtractorThread
from src.db.models import get_session, get_participant, update_session


DATA_DIR = Path(__file__).parent.parent.parent / "data"


class ProcessingScreen(QWidget):
    processing_done = Signal(int)   # session_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_id: int | None = None
        self._worker: ExtractorThread | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        self._lbl_title = QLabel("Extracting Landmarks")
        self._lbl_title.setAlignment(Qt.AlignCenter)
        self._lbl_title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(self._lbl_title)

        self._lbl_status = QLabel("Preparing…")
        self._lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._lbl_status)

        self._progress = QProgressBar()
        self._progress.setFixedWidth(500)
        self._progress.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._progress, alignment=Qt.AlignCenter)

        self._lbl_frames = QLabel("")
        self._lbl_frames.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._lbl_frames)

        self._btn_continue = QPushButton("Continue to Annotation")
        self._btn_continue.setEnabled(False)
        self._btn_continue.setFixedWidth(220)
        self._btn_continue.clicked.connect(lambda: self.processing_done.emit(self._session_id))
        layout.addWidget(self._btn_continue, alignment=Qt.AlignCenter)

    def load_session(self, session_id: int):
        self._session_id = session_id
        self._progress.setValue(0)
        self._btn_continue.setEnabled(False)
        self._lbl_status.setText("Starting extraction…")

        session = get_session(session_id)
        video_path = session["video_path"]
        if not video_path or not Path(video_path).exists():
            QMessageBox.critical(self, "Error", "Video file not found.")
            return

        participant = get_participant(session["participant_id"])
        p_code = participant["participant_code"]
        out_csv = str(DATA_DIR / p_code / f"S{session_id:03d}" / "landmarks.csv")

        self._worker = ExtractorThread(video_path, out_csv)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
            self._lbl_frames.setText(f"Frame {current} / {total}")
            self._lbl_status.setText("Running MediaPipe Hands…")

    def _on_finished(self, csv_path: str):
        update_session(self._session_id, landmarks_path=csv_path, status="processed")
        self._lbl_status.setText("Extraction complete.")
        self._lbl_frames.setText(csv_path)
        self._btn_continue.setEnabled(True)

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Extraction Error", msg)
        self._lbl_status.setText("Error — see above.")
