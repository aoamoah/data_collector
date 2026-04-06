from pathlib import Path

import cv2
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QSizePolicy,
)

from src.annotation.annotator import AnnotationStore, LABELS
from src.db.models import (
    get_session, get_participant, get_annotations_for_session,
    add_annotation, delete_annotation, update_session,
)
from src.export.exporter import export_session


DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATASET_DIR = Path(__file__).parent.parent.parent / "dataset"


class AnnotationScreen(QWidget):
    done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_id: int | None = None
        self._cap: cv2.VideoCapture | None = None
        self._total_frames = 0
        self._current_frame = 0
        self._playing = False
        self._start_mark: int | None = None
        self._store = AnnotationStore()
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_frame)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Video display
        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setMinimumSize(640, 360)
        self._video_label.setStyleSheet("background: #111;")
        self._video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._video_label)

        # Slider
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.valueChanged.connect(self._on_slider)
        root.addWidget(self._slider)

        # Playback controls
        ctrl = QHBoxLayout()
        self._btn_play = QPushButton("Play")
        self._btn_play.setFixedWidth(80)
        self._btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._btn_play)

        self._lbl_frame = QLabel("Frame: 0 / 0")
        ctrl.addWidget(self._lbl_frame)
        ctrl.addStretch()

        self._btn_mark_start = QPushButton("Mark Start")
        self._btn_mark_end = QPushButton("Mark End")
        self._lbl_mark = QLabel("Start: — End: —")
        self._label_combo = QComboBox()
        self._label_combo.addItems(LABELS)
        self._btn_add = QPushButton("Add Annotation")
        self._btn_add.clicked.connect(self._add_annotation)

        for w in (self._btn_mark_start, self._btn_mark_end, self._lbl_mark,
                  self._label_combo, self._btn_add):
            ctrl.addWidget(w)

        self._btn_mark_start.clicked.connect(self._mark_start)
        self._btn_mark_end.clicked.connect(self._mark_end)

        root.addLayout(ctrl)

        # Annotation list + actions
        bottom = QHBoxLayout()
        ann_layout = QVBoxLayout()
        ann_layout.addWidget(QLabel("Annotations:"))
        self._ann_list = QListWidget()
        ann_layout.addWidget(self._ann_list)

        del_btn = QPushButton("Delete Selected")
        del_btn.clicked.connect(self._delete_annotation)
        ann_layout.addWidget(del_btn)
        bottom.addLayout(ann_layout, 2)

        action_layout = QVBoxLayout()
        action_layout.addStretch()

        self._btn_save = QPushButton("Save Labels")
        self._btn_save.setFixedHeight(40)
        self._btn_save.clicked.connect(self._save_labels)
        action_layout.addWidget(self._btn_save)

        self._btn_export = QPushButton("Export Dataset")
        self._btn_export.setFixedHeight(40)
        self._btn_export.clicked.connect(self._export)
        action_layout.addWidget(self._btn_export)

        self._btn_done = QPushButton("Back to Home")
        self._btn_done.clicked.connect(self._on_done)
        action_layout.addWidget(self._btn_done)
        bottom.addLayout(action_layout, 1)

        root.addLayout(bottom)

    def load_session(self, session_id: int):
        self._session_id = session_id
        self._start_mark = None
        self._lbl_mark.setText("Start: — End: —")

        session = get_session(session_id)
        video_path = session["video_path"]
        if not video_path or not Path(video_path).exists():
            QMessageBox.critical(self, "Error", "Video file not found.")
            return

        if self._cap:
            self._cap.release()
        self._cap = cv2.VideoCapture(video_path)
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._slider.setMaximum(max(0, self._total_frames - 1))
        self._current_frame = 0
        self._show_frame(0)

        rows = get_annotations_for_session(session_id)
        self._store.load(rows)
        self._refresh_ann_list()

    def _show_frame(self, index: int):
        if not self._cap:
            return
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = self._cap.read()
        if not ret:
            return
        self._current_frame = index
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(
            self._video_label.width(), self._video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._video_label.setPixmap(pixmap)
        self._lbl_frame.setText(f"Frame: {index} / {self._total_frames - 1}")
        self._slider.blockSignals(True)
        self._slider.setValue(index)
        self._slider.blockSignals(False)

    def _on_slider(self, value: int):
        if not self._playing:
            self._show_frame(value)

    def _toggle_play(self):
        if self._playing:
            self._play_timer.stop()
            self._playing = False
            self._btn_play.setText("Play")
        else:
            fps = self._cap.get(cv2.CAP_PROP_FPS) if self._cap else 30
            interval = max(1, int(1000 / fps))
            self._play_timer.start(interval)
            self._playing = True
            self._btn_play.setText("Pause")

    def _advance_frame(self):
        next_frame = self._current_frame + 1
        if next_frame >= self._total_frames:
            self._toggle_play()
            return
        self._show_frame(next_frame)

    def _mark_start(self):
        self._start_mark = self._current_frame
        self._update_mark_label()

    def _mark_end(self):
        end = self._current_frame
        if self._start_mark is None:
            QMessageBox.warning(self, "Mark", "Mark a start frame first.")
            return
        if end < self._start_mark:
            QMessageBox.warning(self, "Mark", "End frame must be after start frame.")
            return
        self._end_mark = end
        self._update_mark_label()

    def _update_mark_label(self):
        start = self._start_mark if self._start_mark is not None else "—"
        end = getattr(self, "_end_mark", "—")
        self._lbl_mark.setText(f"Start: {start}  End: {end}")

    def _add_annotation(self):
        if self._start_mark is None or not hasattr(self, "_end_mark"):
            QMessageBox.warning(self, "Annotation", "Set both start and end frames first.")
            return
        label = self._label_combo.currentText()
        ann = self._store.add(self._start_mark, self._end_mark, label)
        db_id = add_annotation(self._session_id, self._start_mark, self._end_mark, label)
        ann.db_id = db_id
        self._start_mark = None
        self._end_mark = "—"
        self._lbl_mark.setText("Start: — End: —")
        self._refresh_ann_list()

    def _delete_annotation(self):
        row = self._ann_list.currentRow()
        if row < 0:
            return
        ann = self._store.get_all()[row]
        if ann.db_id:
            delete_annotation(ann.db_id)
        self._store.remove_by_index(row)
        self._refresh_ann_list()

    def _refresh_ann_list(self):
        self._ann_list.clear()
        for ann in self._store.get_all():
            self._ann_list.addItem(
                f"[{ann.start_frame} – {ann.end_frame}]  {ann.label}"
            )

    def _save_labels(self):
        if not self._session_id:
            return
        session = get_session(self._session_id)
        participant = get_participant(session["participant_id"])
        p_code = participant["participant_code"]
        labels_path = str(DATA_DIR / p_code / f"S{self._session_id:03d}" / "labels.csv")
        self._store.save_to_csv(labels_path, self._total_frames)
        update_session(self._session_id, labels_path=labels_path, status="annotated")
        QMessageBox.information(self, "Saved", f"Labels saved to:\n{labels_path}")

    def _export(self):
        try:
            out = export_session(self._session_id, str(DATASET_DIR))
            QMessageBox.information(self, "Exported", f"Dataset exported to:\n{out}")
            update_session(self._session_id, status="exported")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _on_done(self):
        if self._playing:
            self._toggle_play()
        self.done.emit()

    def cleanup(self):
        self._play_timer.stop()
        if self._cap:
            self._cap.release()
            self._cap = None
