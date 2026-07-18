import csv
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QSizePolicy, QCheckBox,
)

from src.annotation.annotator import AnnotationStore, LABELS
from src.annotation.commands import AddAnnotationCommand, RemoveAnnotationCommand, BulkLabelCommand
from src.db.models import (
    get_session, get_participant, get_annotations_for_session,
    add_annotation, delete_annotations_for_session, update_session,
)
from src.db.paths import resolve_data_path
from src.export.exporter import export_session, validate_export


DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATASET_DIR = Path(__file__).parent.parent.parent / "dataset"

# MediaPipe hand skeleton connections (21 landmarks)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]


class AnnotationScreen(QWidget):
    done = Signal()
    reprocess_requested = Signal(int)   # session_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_id: int | None = None
        self._cap: cv2.VideoCapture | None = None
        self._total_frames = 0
        self._current_frame = 0
        self._playing = False
        self._start_mark: int | None = None
        self._end_mark: int | None = None
        self._store = AnnotationStore()
        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_frame)
        # Landmark data: {frame_index: [(x, y, z), ...] or None}
        self._landmarks: dict[int, list | None] = {}
        self._build_ui()
        self._setup_shortcuts()

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

        # Playback controls row
        ctrl = QHBoxLayout()
        self._btn_play = QPushButton("Play")
        self._btn_play.setFixedWidth(80)
        self._btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._btn_play)

        self._lbl_frame = QLabel("Frame: 0 / 0")
        ctrl.addWidget(self._lbl_frame)

        self._chk_landmarks = QCheckBox("Show landmarks")
        self._chk_landmarks.setChecked(True)
        ctrl.addWidget(self._chk_landmarks)

        ctrl.addStretch()

        self._btn_mark_start = QPushButton("Mark Start [S]")
        self._btn_mark_end = QPushButton("Mark End [E]")
        self._lbl_mark = QLabel("Start: — End: —")
        self._label_combo = QComboBox()
        self._label_combo.addItems(LABELS)
        self._btn_add = QPushButton("Add [A]")
        self._btn_add.clicked.connect(self._add_annotation)

        for w in (self._btn_mark_start, self._btn_mark_end, self._lbl_mark,
                  self._label_combo, self._btn_add):
            ctrl.addWidget(w)

        self._btn_mark_start.clicked.connect(self._mark_start)
        self._btn_mark_end.clicked.connect(self._mark_end)
        root.addLayout(ctrl)

        # Annotation list + action buttons
        bottom = QHBoxLayout()
        ann_layout = QVBoxLayout()

        ann_header = QHBoxLayout()
        ann_header.addWidget(QLabel("Annotations:"))
        ann_header.addStretch()
        self._btn_undo = QPushButton("Undo")
        self._btn_undo.setEnabled(False)
        self._btn_undo.setFixedWidth(60)
        self._btn_undo.clicked.connect(self._undo)
        self._btn_redo = QPushButton("Redo")
        self._btn_redo.setEnabled(False)
        self._btn_redo.setFixedWidth(60)
        self._btn_redo.clicked.connect(self._redo)
        ann_header.addWidget(self._btn_undo)
        ann_header.addWidget(self._btn_redo)
        ann_layout.addLayout(ann_header)

        self._ann_list = QListWidget()
        ann_layout.addWidget(self._ann_list)

        ann_actions = QHBoxLayout()
        del_btn = QPushButton("Delete Selected")
        del_btn.clicked.connect(self._delete_annotation)
        ann_actions.addWidget(del_btn)

        bulk_btn = QPushButton("Fill Gaps → not_writing")
        bulk_btn.clicked.connect(self._bulk_label)
        ann_actions.addWidget(bulk_btn)
        ann_layout.addLayout(ann_actions)

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

        self._btn_reextract = QPushButton("Re-extract Landmarks")
        self._btn_reextract.clicked.connect(self._on_reextract)
        action_layout.addWidget(self._btn_reextract)

        self._btn_done = QPushButton("Back to Home")
        self._btn_done.clicked.connect(self._on_done)
        action_layout.addWidget(self._btn_done)
        bottom.addLayout(action_layout, 1)

        root.addLayout(bottom)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Space"), self).activated.connect(self._toggle_play)
        QShortcut(QKeySequence("Left"), self).activated.connect(lambda: self._step_frame(-1))
        QShortcut(QKeySequence("Right"), self).activated.connect(lambda: self._step_frame(1))
        QShortcut(QKeySequence("S"), self).activated.connect(self._mark_start)
        QShortcut(QKeySequence("E"), self).activated.connect(self._mark_end)
        QShortcut(QKeySequence("A"), self).activated.connect(self._add_annotation)
        QShortcut(QKeySequence("W"), self).activated.connect(self._label_writing)
        QShortcut(QKeySequence("N"), self).activated.connect(self._label_not_writing)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self._redo)

    def _label_writing(self):
        self._label_combo.setCurrentText("writing")

    def _label_not_writing(self):
        self._label_combo.setCurrentText("not_writing")

    def _step_frame(self, delta: int):
        target = max(0, min(self._total_frames - 1, self._current_frame + delta))
        self._show_frame(target)

    def load_session(self, session_id: int):
        self._session_id = session_id
        self._start_mark = None
        self._end_mark = None
        self._lbl_mark.setText("Start: — End: —")
        self._landmarks = {}

        session = get_session(session_id)
        video_path = resolve_data_path(session["video_path"])
        if not video_path:
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
        self._update_undo_redo_buttons()

        # Load landmarks if available
        landmarks_path = resolve_data_path(session["landmarks_path"])
        if landmarks_path:
            self._load_landmarks(landmarks_path)

    def _load_landmarks(self, path: str):
        self._landmarks = {}
        try:
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    fi = int(row["frame_index"])
                    if row["hand_detected"] in ("True", "1", "true"):
                        pts = [
                            (float(row[f"l{i}_x"]), float(row[f"l{i}_y"]), float(row[f"l{i}_z"]))
                            for i in range(21)
                        ]
                        self._landmarks[fi] = pts
                    else:
                        self._landmarks[fi] = None
        except Exception:
            self._landmarks = {}

    def _show_frame(self, index: int):
        if not self._cap:
            return
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = self._cap.read()
        if not ret:
            return
        self._current_frame = index

        # Draw landmark overlay if enabled and data available
        if self._chk_landmarks.isChecked() and index in self._landmarks:
            pts = self._landmarks[index]
            if pts:
                h, w = frame.shape[:2]
                for a, b in HAND_CONNECTIONS:
                    ax, ay = int(pts[a][0] * w), int(pts[a][1] * h)
                    bx, by = int(pts[b][0] * w), int(pts[b][1] * h)
                    cv2.line(frame, (ax, ay), (bx, by), (0, 200, 100), 2)
                for x, y, _ in pts:
                    cx, cy = int(x * w), int(y * h)
                    cv2.circle(frame, (cx, cy), 4, (0, 255, 150), -1)

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
        end = self._end_mark if self._end_mark is not None else "—"
        self._lbl_mark.setText(f"Start: {start}  End: {end}")

    def _add_annotation(self):
        if self._start_mark is None or self._end_mark is None:
            QMessageBox.warning(self, "Annotation", "Set both start and end frames first.")
            return
        label = self._label_combo.currentText()
        cmd = AddAnnotationCommand(self._store, self._start_mark, self._end_mark, label)
        self._store.apply_command(cmd)
        self._start_mark = None
        self._end_mark = None
        self._lbl_mark.setText("Start: — End: —")
        self._refresh_ann_list()
        self._update_undo_redo_buttons()

    def _delete_annotation(self):
        row = self._ann_list.currentRow()
        if row < 0:
            return
        ann = self._store.get_all()[row]
        cmd = RemoveAnnotationCommand(self._store, ann)
        self._store.apply_command(cmd)
        self._refresh_ann_list()
        self._update_undo_redo_buttons()

    def _bulk_label(self):
        cmd = BulkLabelCommand(self._store, "not_writing", self._total_frames)
        self._store.apply_command(cmd)
        self._refresh_ann_list()
        self._update_undo_redo_buttons()

    def _undo(self):
        self._store.undo()
        self._refresh_ann_list()
        self._update_undo_redo_buttons()

    def _redo(self):
        self._store.redo()
        self._refresh_ann_list()
        self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        self._btn_undo.setEnabled(self._store.can_undo())
        self._btn_redo.setEnabled(self._store.can_redo())

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

        # Sync annotations to DB (delete all, re-insert from store)
        delete_annotations_for_session(self._session_id)
        for ann in self._store.get_all():
            db_id = add_annotation(self._session_id, ann.start_frame, ann.end_frame, ann.label)
            ann.db_id = db_id

        self._store.save_to_csv(labels_path, self._total_frames)
        update_session(self._session_id, labels_path=labels_path, status="annotated")
        QMessageBox.information(self, "Saved", f"Labels saved to:\n{labels_path}")

    def _export(self):
        if not self._session_id:
            return
        session = get_session(self._session_id)
        warnings = validate_export(session, self._total_frames)
        if warnings:
            msg = "Export warnings:\n\n" + "\n".join(f"• {w}" for w in warnings)
            msg += "\n\nProceed anyway?"
            reply = QMessageBox.warning(
                self, "Export Validation", msg,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        try:
            out = export_session(self._session_id, str(DATASET_DIR))
            QMessageBox.information(self, "Exported", f"Dataset exported to:\n{out}")
            update_session(self._session_id, status="exported")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _on_reextract(self):
        if not self._session_id:
            return
        if self._playing:
            self._toggle_play()
        self.reprocess_requested.emit(self._session_id)

    def _on_done(self):
        if self._playing:
            self._toggle_play()
        self.done.emit()

    def cleanup(self):
        self._play_timer.stop()
        if self._cap:
            self._cap.release()
            self._cap = None
