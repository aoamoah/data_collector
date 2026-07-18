from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QComboBox, QMessageBox,
)

from src.config import AppConfig
from src.processing.extractor import ExtractorThread
from src.ui.quality_report_dialog import QualityReportDialog
from src.db.models import get_session, get_participant, update_session, save_quality_report
from src.db.paths import resolve_data_path


DATA_DIR = Path(__file__).parent.parent.parent / "data"


class ProcessingScreen(QWidget):
    processing_done = Signal(int)   # session_id

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
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

        # Tracked-hand selector: defaults to the session's dominant hand,
        # lets the user re-run when the wrong hand was picked
        hand_row = QHBoxLayout()
        hand_row.setAlignment(Qt.AlignCenter)
        hand_row.addWidget(QLabel("Tracked hand:"))
        self._hand_combo = QComboBox()
        self._hand_combo.addItems(["right", "left", "either"])
        self._hand_combo.setToolTip(
            "Choose 'either' when the participant switched hands mid-video —\n"
            "the most confident hand is tracked in each frame."
        )
        hand_row.addWidget(self._hand_combo)
        self._btn_rerun = QPushButton("Re-run Extraction")
        self._btn_rerun.clicked.connect(self._start_extraction)
        hand_row.addWidget(self._btn_rerun)
        layout.addLayout(hand_row)

        self._btn_continue = QPushButton("Continue to Annotation")
        self._btn_continue.setEnabled(False)
        self._btn_continue.setFixedWidth(220)
        self._btn_continue.clicked.connect(lambda: self.processing_done.emit(self._session_id))
        layout.addWidget(self._btn_continue, alignment=Qt.AlignCenter)

        self._btn_back = QPushButton("Back to Home")
        self._btn_back.setFixedWidth(220)
        self._btn_back.clicked.connect(lambda: self.window().show_home())
        layout.addWidget(self._btn_back, alignment=Qt.AlignCenter)

    def apply_config(self, config: AppConfig):
        self._config = config

    def load_session(self, session_id: int):
        self._session_id = session_id
        session = get_session(session_id)
        hand = (session["dominant_hand"] or "right").lower()
        self._hand_combo.setCurrentText(hand)
        self._start_extraction()

    def _start_extraction(self):
        self._progress.setValue(0)
        self._btn_continue.setEnabled(False)
        self._btn_back.setEnabled(False)
        self._btn_rerun.setEnabled(False)
        self._hand_combo.setEnabled(False)
        self._lbl_status.setText("Starting extraction…")

        session = get_session(self._session_id)
        video_path = resolve_data_path(session["video_path"])
        if not video_path:
            QMessageBox.critical(self, "Error", "Video file not found.")
            self._lbl_status.setText("Video file not found.")
            self._btn_back.setEnabled(True)
            return

        participant = get_participant(session["participant_id"])
        p_code = participant["participant_code"]
        out_csv = str(DATA_DIR / p_code / f"S{self._session_id:03d}" / "landmarks.csv")

        self._worker = ExtractorThread(
            video_path, out_csv,
            confidence_threshold=self._config.confidence_threshold,
            target_hand=self._hand_combo.currentText(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.quality_ready.connect(self._on_quality_ready)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)
            self._lbl_frames.setText(f"Frame {current} / {total}")
            self._lbl_status.setText("Running MediaPipe Hands…")

    def _on_quality_ready(self, report: dict):
        if self._session_id:
            save_quality_report(self._session_id, report)
        dlg = QualityReportDialog(report, self)
        dlg.exec()

    def _on_finished(self, csv_path: str):
        # Re-extraction must not downgrade a session that is already
        # annotated or exported
        status = get_session(self._session_id)["status"]
        if status not in ("annotated", "exported"):
            status = "processed"
        update_session(self._session_id, landmarks_path=csv_path, status=status)
        self._lbl_status.setText("Extraction complete.")
        self._lbl_frames.setText(csv_path)
        self._btn_continue.setEnabled(True)
        self._btn_back.setEnabled(True)
        self._btn_rerun.setEnabled(True)
        self._hand_combo.setEnabled(True)

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Extraction Error", msg)
        self._lbl_status.setText("Error — see above.")
        self._btn_back.setEnabled(True)
        self._btn_rerun.setEnabled(True)
        self._hand_combo.setEnabled(True)
