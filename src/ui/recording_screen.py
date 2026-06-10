import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage, QPainter, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QFileDialog,
)

from src.capture.camera import CameraThread, find_available_camera
from src.config import AppConfig
from src.task_guide.guide import TaskGuide, TASK_STEPS
from src.db.models import update_session, get_participant, get_session


DATA_DIR = Path(__file__).parent.parent.parent / "data"

_COUNTDOWN_SECONDS = 3


class RecordingScreen(QWidget):
    recording_done = Signal(int)   # session_id

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._session_id: int | None = None
        self._camera: CameraThread | None = None
        self._guide = TaskGuide(self)
        self._recording = False
        self._frame_count = 0
        self._fps_display = 0.0
        self._hand_detected = False

        # Countdown state
        self._countdown_active = False
        self._countdown_value = 0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._countdown_tick)

        self._build_ui()
        self._guide.step_changed.connect(self._on_step_changed)
        self._guide.tick.connect(self._on_tick)
        self._guide.completed.connect(self._on_guide_completed)

    def _build_ui(self):
        root = QHBoxLayout(self)

        # Left: camera preview
        left = QVBoxLayout()
        self._preview = QLabel("Camera preview")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumSize(640, 480)
        self._preview.setStyleSheet("background: #111; color: #666; border: 3px solid #333;")
        left.addWidget(self._preview)

        stats = QHBoxLayout()
        self._lbl_fps = QLabel("FPS: --")
        self._lbl_frames = QLabel("Frames: 0")
        stats.addWidget(self._lbl_fps)
        stats.addStretch()
        stats.addWidget(self._lbl_frames)
        left.addLayout(stats)

        btn_row = QHBoxLayout()
        self._btn_record = QPushButton("Start Recording")
        self._btn_record.setFixedHeight(44)
        self._btn_record.setEnabled(False)
        self._btn_record.clicked.connect(self._toggle_recording)
        btn_row.addWidget(self._btn_record)

        self._btn_settings = QPushButton("Settings")
        self._btn_settings.setFixedHeight(44)
        self._btn_settings.clicked.connect(self._open_settings)
        btn_row.addWidget(self._btn_settings)
        left.addLayout(btn_row)

        self._btn_load_video = QPushButton("Load Existing Video…")
        self._btn_load_video.setFixedHeight(36)
        self._btn_load_video.clicked.connect(self._load_existing_video)
        left.addWidget(self._btn_load_video)

        self._btn_back = QPushButton("Back")
        self._btn_back.clicked.connect(self._on_back)
        left.addWidget(self._btn_back)

        root.addLayout(left, 3)

        # Right: task guide
        right = QVBoxLayout()
        right.setSpacing(12)

        self._lbl_step_name = QLabel("—")
        self._lbl_step_name.setStyleSheet("font-size: 20px; font-weight: bold;")
        self._lbl_step_name.setAlignment(Qt.AlignCenter)
        right.addWidget(self._lbl_step_name)

        self._lbl_instruction = QLabel("")
        self._lbl_instruction.setWordWrap(True)
        self._lbl_instruction.setAlignment(Qt.AlignCenter)
        self._lbl_instruction.setStyleSheet("font-size: 14px;")
        right.addWidget(self._lbl_instruction)

        self._lbl_countdown = QLabel("")
        self._lbl_countdown.setAlignment(Qt.AlignCenter)
        self._lbl_countdown.setStyleSheet("font-size: 48px; font-weight: bold; color: #3a8;")
        right.addWidget(self._lbl_countdown)

        self._progress_steps = QProgressBar()
        self._progress_steps.setMaximum(len(TASK_STEPS))
        self._progress_steps.setValue(0)
        right.addWidget(self._progress_steps)

        self._btn_skip = QPushButton("Skip Step")
        self._btn_skip.setEnabled(False)
        self._btn_skip.clicked.connect(self._guide.skip)
        right.addWidget(self._btn_skip)

        self._btn_start_guide = QPushButton("Start Task Guide")
        self._btn_start_guide.setEnabled(False)
        self._btn_start_guide.clicked.connect(self._start_guide)
        right.addWidget(self._btn_start_guide)

        right.addStretch()
        root.addLayout(right, 1)

    def apply_config(self, config: AppConfig):
        self._config = config
        self._rebuild_guide()

    def _rebuild_guide(self):
        self._guide.stop()
        self._guide = TaskGuide(
            self,
            durations=self._config.task_durations,
            audio_cues=self._config.audio_cues,
        )
        self._guide.step_changed.connect(self._on_step_changed)
        self._guide.tick.connect(self._on_tick)
        self._guide.completed.connect(self._on_guide_completed)

    def load_session(self, session_id: int):
        self._session_id = session_id
        self._frame_count = 0
        self._recording = False
        self._hand_detected = False
        self._btn_record.setText("Start Recording")
        self._btn_record.setEnabled(False)
        self._btn_start_guide.setEnabled(False)
        self._lbl_step_name.setText("Detecting camera…")
        self._lbl_instruction.setText("")
        self._lbl_countdown.setText("")
        self._progress_steps.setValue(0)
        self._preview.setStyleSheet("background: #111; color: #666; border: 3px solid #333;")

        if self._camera:
            self._camera.stop()
            self._camera = None

        self._rebuild_guide()

        camera_index = find_available_camera()
        if camera_index is None:
            self._on_no_camera()
            return

        session = get_session(session_id)
        dominant_hand = session["dominant_hand"] if session else "right"

        self._camera = CameraThread(
            camera_index,
            resolution=self._config.resolution,
            fps=self._config.fps,
            dominant_hand=dominant_hand,
        )
        self._camera.frame_ready.connect(self._on_frame)
        self._camera.hand_presence.connect(self._on_hand_presence)
        self._camera.error.connect(self._on_camera_error)
        self._camera.start()
        QTimer.singleShot(1000, self._camera_ready)

    def _on_no_camera(self):
        self._preview.setText(
            "No camera detected.\n\n"
            "Use 'Load Existing Video' to process a pre-recorded file."
        )
        self._lbl_step_name.setText("No Camera")
        self._lbl_instruction.setText("You can still run the task guide or load a video.")
        self._btn_start_guide.setEnabled(True)

    def _camera_ready(self):
        self._btn_record.setEnabled(True)
        self._btn_start_guide.setEnabled(True)
        self._lbl_step_name.setText("Ready")
        self._lbl_instruction.setText("Press 'Start Task Guide' to begin, then 'Start Recording'.")

    def _on_hand_presence(self, detected: bool):
        self._hand_detected = detected
        color = "#22aa44" if detected else "#aa2222"
        self._preview.setStyleSheet(
            f"background: #111; color: #666; border: 3px solid {color};"
        )

    def _on_frame(self, image: QImage, fps: float):
        self._fps_display = fps

        if self._countdown_active:
            # Paint countdown number over the frame
            pixmap = QPixmap.fromImage(image).scaled(
                self._preview.width(), self._preview.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            painter = QPainter(pixmap)
            painter.setFont(QFont("Arial", 96, QFont.Bold))
            painter.setPen(QColor(255, 80, 80))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, str(self._countdown_value))
            painter.end()
            self._preview.setPixmap(pixmap)
        else:
            pixmap = QPixmap.fromImage(image).scaled(
                self._preview.width(), self._preview.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._preview.setPixmap(pixmap)

        if self._recording:
            self._frame_count += 1
            self._lbl_frames.setText(f"Frames: {self._frame_count}")
        self._lbl_fps.setText(f"FPS: {fps:.1f}")

    def _on_camera_error(self, msg: str):
        self._on_no_camera()

    def _open_settings(self):
        from src.ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            self._config = dlg.get_config()

    def _load_existing_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv)"
        )
        if not path or not self._session_id:
            return
        session = get_session(self._session_id)
        participant = get_participant(session["participant_id"])
        p_code = participant["participant_code"]
        out_dir = DATA_DIR / p_code / f"S{self._session_id:03d}"
        out_dir.mkdir(parents=True, exist_ok=True)

        dest = str(out_dir / "video.mp4")
        if path != dest:
            shutil.copy2(path, dest)

        update_session(self._session_id, status="recorded", video_path=dest)
        self.recording_done.emit(self._session_id)

    def _start_guide(self):
        self._progress_steps.setValue(0)
        self._btn_skip.setEnabled(True)
        self._guide.start()

    def _on_step_changed(self, index: int, name: str, instruction: str, _total: int):
        self._lbl_step_name.setText(f"Step {index + 1}/{len(TASK_STEPS)}: {name}")
        self._lbl_instruction.setText(instruction)
        self._progress_steps.setValue(index + 1)

    def _on_tick(self, _index: int, remaining: int):
        self._lbl_countdown.setText(str(remaining))

    def _on_guide_completed(self):
        self._lbl_step_name.setText("Guide complete")
        self._lbl_instruction.setText("Stop recording when ready.")
        self._lbl_countdown.setText("")
        self._btn_skip.setEnabled(False)

    def _toggle_recording(self):
        if self._countdown_active:
            return
        if not self._recording:
            self._begin_countdown()
        else:
            self._stop_recording()

    def _begin_countdown(self):
        self._countdown_active = True
        self._countdown_value = _COUNTDOWN_SECONDS
        self._btn_record.setEnabled(False)
        self._countdown_timer.start()

    def _countdown_tick(self):
        if self._countdown_value <= 0:
            self._countdown_timer.stop()
            self._countdown_active = False
            self._btn_record.setEnabled(True)
            self._start_recording()
            return
        self._countdown_value -= 1

    def _start_recording(self):
        session = get_session(self._session_id)
        participant = get_participant(session["participant_id"])
        p_code = participant["participant_code"]
        out_dir = DATA_DIR / p_code / f"S{self._session_id:03d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = str(out_dir / "video.mp4")

        w, h = self._config.resolution
        self._camera.start_recording(video_path, fps=float(self._config.fps), width=w, height=h)
        self._recording = True
        self._frame_count = 0
        self._btn_record.setText("Stop Recording")
        update_session(self._session_id, status="recording", video_path=video_path)

    def _stop_recording(self):
        path = self._camera.stop_recording()
        self._recording = False
        self._btn_record.setText("Start Recording")
        self._guide.stop()
        update_session(self._session_id, status="recorded")
        self.recording_done.emit(self._session_id)

    def _on_back(self):
        if self._recording:
            self._stop_recording()
        if self._camera:
            self._camera.stop()
        self.window().show_home()

    def cleanup(self):
        self._guide.stop()
        self._countdown_timer.stop()
        if self._camera:
            self._camera.stop()
