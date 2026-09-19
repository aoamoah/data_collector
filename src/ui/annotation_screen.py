import csv
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QSizePolicy, QCheckBox, QSplitter, QTextBrowser,
)

from src.annotation.annotator import AnnotationStore, LABELS, DEFAULT_LABEL
from src.annotation.commands import AddAnnotationCommand, RemoveAnnotationCommand, BulkLabelCommand
from src.annotation.labelling_guide import LABEL_RULES, guide_html
from src.db.models import (
    get_session, get_participant, get_annotations_for_session, get_all_sessions,
    add_annotation, delete_annotations_for_session, update_session,
)
from src.db.paths import resolve_data_path
from src.export.exporter import export_session, validate_export
from src.processing.video_io import proxy_path_for
from src.ui.label_timeline import LabelTimeline, LABEL_COLORS


# Hex colour of each label as drawn on the timeline; None is unlabelled
LABEL_HEX = {label: color.name() for label, color in LABEL_COLORS.items()}

DATA_DIR = Path(__file__).parent.parent.parent / "data"
# Sessions with landmarks, i.e. the ones this screen can open
ANNOTATABLE_STATUSES = ("processed", "annotated", "exported")
PLAYBACK_SPEEDS = [("0.25×", 0.25), ("0.5×", 0.5), ("1×", 1.0), ("2×", 2.0)]

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
        self._landmark_rows = 0
        # Annotations as last loaded or saved, to tell whether leaving the
        # session would lose work
        self._saved_snapshot: list[tuple] = []
        # Every annotatable session in navigation order (participant, then id)
        self._nav_sessions: list = []
        self._build_ui()
        self._setup_shortcuts()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # Session bar: move to another session without going back to Home
        nav = QHBoxLayout()
        self._btn_prev_session = QPushButton("◀ Prev Session [PgUp]")
        self._btn_prev_session.clicked.connect(lambda: self._step_session(-1))
        nav.addWidget(self._btn_prev_session)
        nav.addWidget(QLabel("Participant:"))
        self._nav_participant = QComboBox()
        self._nav_participant.setMinimumWidth(160)
        self._nav_participant.activated.connect(self._on_nav_participant)
        nav.addWidget(self._nav_participant)
        nav.addWidget(QLabel("Session:"))
        self._nav_session = QComboBox()
        self._nav_session.setMinimumWidth(160)
        self._nav_session.activated.connect(self._on_nav_session)
        nav.addWidget(self._nav_session)
        self._btn_next_session = QPushButton("Next Session [PgDown] ▶")
        self._btn_next_session.clicked.connect(lambda: self._step_session(1))
        nav.addWidget(self._btn_next_session)
        self._lbl_nav_pos = QLabel("")
        nav.addWidget(self._lbl_nav_pos)
        nav.addStretch()
        root.addLayout(nav)

        # Video column on the left, labelling guide on the right
        splitter = QSplitter(Qt.Horizontal)
        video_col = QWidget()
        video_layout = QVBoxLayout(video_col)
        video_layout.setContentsMargins(0, 0, 0, 0)

        # Video display
        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setMinimumSize(480, 360)
        self._video_label.setStyleSheet("background: #111;")
        self._video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout.addWidget(self._video_label)

        # Slider
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.valueChanged.connect(self._on_slider)
        video_layout.addWidget(self._slider)

        self._timeline = LabelTimeline()
        self._timeline.seek_requested.connect(self._on_timeline_seek)
        video_layout.addWidget(self._timeline)

        swatches = [(LABEL_HEX[label], label) for label in LABELS]
        swatches += [(LABEL_HEX[None], "unlabelled"), ("#4da3ff", "marked range")]
        legend = QLabel("   ".join(
            f'<span style="color:{color}; font-size:14px;">■</span> {name}'
            for color, name in swatches))
        video_layout.addWidget(legend)

        # Says whether the frame on screen is guaranteed to be the frame the
        # landmarks and labels refer to
        self._lbl_source = QLabel("")
        self._lbl_source.setWordWrap(True)
        video_layout.addWidget(self._lbl_source)
        splitter.addWidget(video_col)

        self._guide = QTextBrowser()
        self._guide.setHtml(guide_html(LABEL_HEX))
        self._guide.setMinimumWidth(260)
        splitter.addWidget(self._guide)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        root.addWidget(splitter, 1)

        # Playback controls row
        ctrl = QHBoxLayout()
        self._btn_play = QPushButton("Play")
        self._btn_play.setFixedWidth(80)
        self._btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self._btn_play)

        self._speed_combo = QComboBox()
        for text, speed in PLAYBACK_SPEEDS:
            self._speed_combo.addItem(text, speed)
        self._speed_combo.setCurrentIndex(2)
        self._speed_combo.setToolTip("Playback speed — slow down to place the "
                                     "boundaries of short pauses")
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        ctrl.addWidget(self._speed_combo)

        self._lbl_frame = QLabel("Frame: 0 / 0")
        ctrl.addWidget(self._lbl_frame)

        self._chk_landmarks = QCheckBox("Show landmarks")
        self._chk_landmarks.setChecked(True)
        ctrl.addWidget(self._chk_landmarks)

        self._btn_guide = QPushButton("Guide [F1]")
        self._btn_guide.setCheckable(True)
        self._btn_guide.setChecked(True)
        self._btn_guide.setToolTip("Show or hide the labelling guide")
        self._btn_guide.toggled.connect(self._guide.setVisible)
        ctrl.addWidget(self._btn_guide)

        ctrl.addStretch()

        self._btn_mark_start = QPushButton("Mark Start [S]")
        self._btn_mark_end = QPushButton("Mark End [E]")
        self._lbl_mark = QLabel("Start: — End: —")
        self._label_combo = QComboBox()
        self._label_combo.addItems(LABELS)
        for i, label in enumerate(LABELS):
            self._label_combo.setItemData(i, LABEL_RULES[label], Qt.ToolTipRole)
        self._label_combo.currentTextChanged.connect(self._update_label_hint)
        self._btn_add = QPushButton("Add [A]")
        self._btn_add.clicked.connect(self._add_annotation)

        for w in (self._btn_mark_start, self._btn_mark_end, self._lbl_mark,
                  self._label_combo, self._btn_add):
            ctrl.addWidget(w)

        self._btn_mark_start.clicked.connect(self._mark_start)
        self._btn_mark_end.clicked.connect(self._mark_end)
        root.addLayout(ctrl)

        # What the label about to be added means, so the rule is in view at
        # the moment of choosing it
        self._lbl_hint = QLabel()
        self._lbl_hint.setWordWrap(True)
        root.addWidget(self._lbl_hint)
        self._update_label_hint(self._label_combo.currentText())

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
        QShortcut(QKeySequence("U"), self).activated.connect(self._label_unsure)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self._redo)
        QShortcut(QKeySequence("F1"), self).activated.connect(self._btn_guide.toggle)
        QShortcut(QKeySequence("PgUp"), self).activated.connect(lambda: self._step_session(-1))
        QShortcut(QKeySequence("PgDown"), self).activated.connect(lambda: self._step_session(1))

    def _update_label_hint(self, label: str):
        self._lbl_hint.setText(
            f'Adding as <b style="color:{LABEL_HEX[label]};">{label}</b>: '
            f"{LABEL_RULES[label]}")

    def _label_writing(self):
        self._label_combo.setCurrentText("writing")

    def _label_not_writing(self):
        self._label_combo.setCurrentText("not_writing")

    def _label_unsure(self):
        self._label_combo.setCurrentText("unsure")

    def _step_frame(self, delta: int):
        target = max(0, min(self._total_frames - 1, self._current_frame + delta))
        self._show_frame(target)

    # ---------- Session navigation ----------

    def _snapshot(self) -> list[tuple]:
        return [(a.start_frame, a.end_frame, a.label) for a in self._store.get_all()]

    def has_unsaved_changes(self) -> bool:
        return self._session_id is not None and self._snapshot() != self._saved_snapshot

    def confirm_leave(self) -> bool:
        """True when it is safe to leave this session: nothing unsaved, or the
        user chose to save or discard it."""
        if not self.has_unsaved_changes():
            return True
        reply = QMessageBox.question(
            self, "Unsaved labels",
            f"Session {self._session_id} has label changes that are not saved.\n\n"
            "Save them before leaving?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if reply == QMessageBox.Save:
            return self._save_labels()
        return reply == QMessageBox.Discard

    def _open_other_session(self, session_id: int):
        if session_id == self._session_id:
            return
        if not self.confirm_leave():
            self._refresh_nav()   # put the dropdowns back on this session
            return
        if self._playing:
            self._toggle_play()
        self.load_session(session_id)

    def _step_session(self, delta: int):
        ids = [s["id"] for s in self._nav_sessions]
        if self._session_id not in ids:
            return
        i = ids.index(self._session_id) + delta
        if 0 <= i < len(ids):
            self._open_other_session(ids[i])

    def _on_nav_participant(self, index: int):
        code = self._nav_participant.itemData(index)
        theirs = [s for s in self._nav_sessions if s["participant_code"] == code]
        if not theirs:
            return
        # Land on the first session still waiting for labels, if any
        todo = [s for s in theirs if s["status"] == "processed"]
        self._open_other_session((todo or theirs)[0]["id"])

    def _on_nav_session(self, index: int):
        self._open_other_session(self._nav_session.itemData(index))

    def _refresh_nav(self):
        """Rebuild the session bar from the DB, selecting the open session."""
        self._nav_sessions = [s for s in get_all_sessions()
                              if s["status"] in ANNOTATABLE_STATUSES]
        current = next((s for s in self._nav_sessions
                        if s["id"] == self._session_id), None)
        codes = list(dict.fromkeys(s["participant_code"] for s in self._nav_sessions))

        self._nav_participant.blockSignals(True)
        self._nav_session.blockSignals(True)
        self._nav_participant.clear()
        for code in codes:
            theirs = [s for s in self._nav_sessions if s["participant_code"] == code]
            done = sum(s["status"] != "processed" for s in theirs)
            self._nav_participant.addItem(f"{code}  ({done}/{len(theirs)} labelled)", code)
        self._nav_session.clear()
        if current is not None:
            self._nav_participant.setCurrentIndex(codes.index(current["participant_code"]))
            for s in self._nav_sessions:
                if s["participant_code"] != current["participant_code"]:
                    continue
                flagged = "  [FLAGGED]" if s["flagged"] else ""
                self._nav_session.addItem(f"S{s['id']:03d}  [{s['status']}]{flagged}", s["id"])
                if s["id"] == current["id"]:
                    self._nav_session.setCurrentIndex(self._nav_session.count() - 1)
        self._nav_participant.blockSignals(False)
        self._nav_session.blockSignals(False)

        ids = [s["id"] for s in self._nav_sessions]
        pos = ids.index(self._session_id) if current is not None else -1
        self._btn_prev_session.setEnabled(pos > 0)
        self._btn_next_session.setEnabled(0 <= pos < len(ids) - 1)
        self._lbl_nav_pos.setText(f"{pos + 1} of {len(ids)}" if pos >= 0 else "")

    def load_session(self, session_id: int):
        self._session_id = session_id
        self._start_mark = None
        self._end_mark = None
        self._update_mark_label()
        self._landmarks = {}

        self._store.load([])
        self._saved_snapshot = []
        self._refresh_ann_list()
        self._refresh_nav()

        session = get_session(session_id)
        video_path = resolve_data_path(session["video_path"])
        if not video_path:
            QMessageBox.critical(self, "Error", "Video file not found.")
            return

        # Landmarks first: their row count is the frame count every label
        # must line up with
        landmarks_path = resolve_data_path(session["landmarks_path"])
        self._landmark_rows = 0
        if landmarks_path:
            self._load_landmarks(landmarks_path)

        # Prefer the frame-exact proxy the extractor wrote (see video_io);
        # seeking the original is not reliable on every container
        proxy = proxy_path_for(landmarks_path)
        use_proxy = proxy is not None and proxy.exists()
        if self._cap:
            self._cap.release()
        self._cap = cv2.VideoCapture(str(proxy) if use_proxy else video_path)
        video_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._total_frames = self._landmark_rows or video_frames
        if use_proxy and video_frames == self._landmark_rows:
            self._lbl_source.setText("Frame-exact: showing the annotation proxy, "
                                     "frame N here is row N of landmarks.csv.")
            self._lbl_source.setStyleSheet("color: #2e9d5b;")
        else:
            reason = ("no annotation proxy — re-extract landmarks to build one"
                      if not use_proxy else
                      f"proxy has {video_frames} frames, landmarks {self._landmark_rows}"
                      " — re-extract landmarks")
            self._lbl_source.setText(
                f"Seeking may be inexact ({reason}). On some containers the frame "
                "shown can lag the frame index by several frames.")
            self._lbl_source.setStyleSheet("color: #d9822b;")
        self._slider.setMaximum(max(0, self._total_frames - 1))
        self._current_frame = 0

        rows = get_annotations_for_session(session_id)
        self._store.load(rows)
        self._saved_snapshot = self._snapshot()
        self._refresh_ann_list()
        self._update_undo_redo_buttons()
        self._show_frame(0)

    def _load_landmarks(self, path: str):
        self._landmarks = {}
        try:
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    fi = int(row["frame_index"])
                    self._landmark_rows = max(self._landmark_rows, fi + 1)
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
            self._landmark_rows = 0

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
        label = self._store.label_at(index)
        self._lbl_frame.setText(
            f"Frame: {index} / {self._total_frames - 1}  ·  "
            f'<b style="color:{LABEL_HEX.get(label, LABEL_HEX[None])};">'
            f"{label or 'unlabelled'}</b>")
        self._slider.blockSignals(True)
        self._slider.setValue(index)
        self._slider.blockSignals(False)
        self._timeline.set_position(index)

    def _on_slider(self, value: int):
        if not self._playing:
            self._show_frame(value)

    def _on_timeline_seek(self, frame: int):
        if self._playing:
            self._toggle_play()
        self._show_frame(frame)

    def _playback_interval(self) -> int:
        fps = (self._cap.get(cv2.CAP_PROP_FPS) if self._cap else 0) or 30
        return max(1, int(1000 / (fps * self._speed_combo.currentData())))

    def _on_speed_changed(self, _index: int):
        if self._playing:
            self._play_timer.start(self._playback_interval())

    def _toggle_play(self):
        if self._playing:
            self._play_timer.stop()
            self._playing = False
            self._btn_play.setText("Play")
        else:
            self._play_timer.start(self._playback_interval())
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
        self._end_mark = None
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
        self._timeline.set_marks(self._start_mark, self._end_mark)

    def _add_annotation(self):
        if self._start_mark is None or self._end_mark is None:
            QMessageBox.warning(self, "Annotation", "Set both start and end frames first.")
            return
        label = self._label_combo.currentText()
        cmd = AddAnnotationCommand(self._store, self._start_mark, self._end_mark, label)
        self._store.apply_command(cmd)
        self._start_mark = None
        self._end_mark = None
        self._update_mark_label()
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
                f"  ({ann.end_frame - ann.start_frame + 1} fr)"
            )
        self._timeline.set_labels(self._store.frame_labels(self._total_frames))

    def _save_labels(self) -> bool:
        if not self._session_id:
            return False
        session = get_session(self._session_id)
        participant = get_participant(session["participant_id"])
        p_code = participant["participant_code"]
        labels_path = str(DATA_DIR / p_code / f"S{self._session_id:03d}" / "labels.csv")

        uncovered = sum(e - s + 1 for s, e in self._store.uncovered_runs(self._total_frames))
        if uncovered:
            reply = QMessageBox.question(
                self, "Unlabelled frames",
                f"{uncovered} of {self._total_frames} frames have no label and will "
                f"be saved as {DEFAULT_LABEL}.\n\nSave anyway? (Use 'Fill Gaps' to "
                "make that explicit, or label them first.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return False

        # Sync annotations to DB (delete all, re-insert from store)
        delete_annotations_for_session(self._session_id)
        for ann in self._store.get_all():
            db_id = add_annotation(self._session_id, ann.start_frame, ann.end_frame, ann.label)
            ann.db_id = db_id

        self._store.save_to_csv(labels_path, self._total_frames)
        update_session(self._session_id, labels_path=labels_path, status="annotated")
        self._saved_snapshot = self._snapshot()
        self._refresh_nav()
        QMessageBox.information(self, "Saved", f"Labels saved to:\n{labels_path}")
        return True

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
            out = export_session(self._session_id)
            QMessageBox.information(self, "Exported", f"Dataset exported to:\n{out}")
            update_session(self._session_id, status="exported")
            self._refresh_nav()
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _on_reextract(self):
        if not self._session_id:
            return
        if not self.confirm_leave():
            return
        if self._playing:
            self._toggle_play()
        self.reprocess_requested.emit(self._session_id)

    def _on_done(self):
        if not self.confirm_leave():
            return
        if self._playing:
            self._toggle_play()
        self.done.emit()

    def cleanup(self):
        self._play_timer.stop()
        if self._cap:
            self._cap.release()
            self._cap = None
