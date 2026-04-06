from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QFileDialog,
)

from src.capture.camera import CameraThread, find_available_camera
from src.task_guide.guide import TaskGuide, TASK_STEPS
from src.db.models import update_session, get_participant, get_session


DATA_DIR = Path(__file__).parent.parent.parent / "data"


class RecordingScreen(QWidget):
    recording_done = Signal(int)   # session_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_id: int | None = None
        self._camera: CameraThread | None = None
        self._guide = TaskGuide(self)
        self._recording = False
        self._frame_count = 0
        self._fps_display = 0.0

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
        self._preview.setStyleSheet("background: #111; color: #666;")
        left.addWidget(self._preview)

        stats = QHBoxLayout()
        self._lbl_fps = QLabel("FPS: --")
        self._lbl_frames = QLabel("Frames: 0")
        stats.addWidget(self._lbl_fps)
        stats.addStretch()
        stats.addWidget(self._lbl_frames)
        left.addLayout(stats)

        self._btn_record = QPushButton("Start Recording")
        self._btn_record.setFixedHeight(44)
        self._btn_record.setEnabled(False)
        self._btn_record.clicked.connect(self._toggle_recording)
        left.addWidget(self._btn_record)

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

    def load_session(self, session_id: int):
        self._session_id = session_id
        self._frame_count = 0
        self._recording = False
        self._btn_record.setText("Start Recording")
        self._btn_record.setEnabled(False)
        self._btn_start_guide.setEnabled(False)
        self._lbl_step_name.setText("Detecting camera…")
        self._lbl_instruction.setText("")
        self._lbl_countdown.setText("")
        self._progress_steps.setValue(0)

        if self._camera:
            self._camera.stop()
            self._camera = None

        camera_index = find_available_camera()
        if camera_index is None:
            self._on_no_camera()
            return

        self._camera = CameraThread(camera_index)
        self._camera.frame_ready.connect(self._on_frame)
        self._camera.error.connect(self._on_camera_error)
        self._camera.start()
        QTimer.singleShot(1000, self._camera_ready)

    def _on_no_camera(self):
        self._preview.setText(
            "No camera detected.\n\n"
            "On WSL2, attach your webcam via usbipd-win,\n"
            "or use 'Load Existing Video' to process a pre-recorded file."
        )
        self._lbl_step_name.setText("No Camera")
        self._lbl_instruction.setText("You can still run the task guide or load a video.")
        self._btn_start_guide.setEnabled(True)

    def _camera_ready(self):
        self._btn_record.setEnabled(True)
        self._btn_start_guide.setEnabled(True)
        self._lbl_step_name.setText("Ready")
        self._lbl_instruction.setText("Press 'Start Task Guide' to begin, then 'Start Recording'.")

    def _on_frame(self, image: QImage, fps: float):
        self._fps_display = fps
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

        import shutil
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
        if not self._recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        session = get_session(self._session_id)
        participant = get_participant(session["participant_id"])
        p_code = participant["participant_code"]
        out_dir = DATA_DIR / p_code / f"S{self._session_id:03d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = str(out_dir / "video.mp4")

        self._camera.start_recording(video_path, fps=30.0, width=640, height=480)
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
        # Navigate back — handled by MainWindow
        self.parent().show_home()

    def cleanup(self):
        self._guide.stop()
        if self._camera:
            self._camera.stop()
