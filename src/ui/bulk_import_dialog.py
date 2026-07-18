"""Bulk import: turn a batch of video files or image sequences (WITA / IPN
downloads) into sessions — one session per item — and run landmark
extraction on each."""

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QListWidget, QPushButton, QProgressBar, QFileDialog, QMessageBox,
    QDialogButtonBox, QSpinBox,
)

from src.config import AppConfig
from src.db.models import (
    get_all_participants, get_participant, add_session, update_session,
    save_quality_report,
)
from src.export.exporter import DATASET_FOLDERS
from src.processing.extractor import ExtractorThread
from src.processing.sequence_converter import (
    SequenceConverterThread, find_sequences, list_sequence,
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
VIDEO_FILTER = "Video Files (*.mp4 *.avi *.mov *.mkv *.webm)"


class BulkImportDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Import Videos")
        self.setMinimumSize(560, 480)
        self._config = config
        # each item: {"type": "video"|"sequence", "path": str, "label": str}
        self._items: list[dict] = []
        self._worker: ExtractorThread | None = None
        self._converter: SequenceConverterThread | None = None
        self._queue: list[tuple[int, dict]] = []   # (session_id, item)
        self._current = 0
        self._imported: list[int] = []
        self._errors: list[str] = []
        self._cancelled = False

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._dataset = QComboBox()
        self._dataset.addItems(DATASET_FOLDERS)
        form.addRow("Dataset", self._dataset)

        self._participant = QComboBox()
        self._participants = get_all_participants()
        for p in self._participants:
            self._participant.addItem(p["participant_code"], p["id"])
        form.addRow("Participant", self._participant)

        self._hand = QComboBox()
        self._hand.addItems(["right", "left", "either"])
        self._hand.setToolTip("Hand tracked during extraction. 'either' keeps "
                              "the most confident hand per frame.")
        form.addRow("Tracked hand", self._hand)

        self._seq_fps = QSpinBox()
        self._seq_fps.setRange(1, 120)
        self._seq_fps.setValue(30)
        self._seq_fps.setToolTip("Frame rate used when converting PNG "
                                 "sequences to video.")
        form.addRow("Sequence FPS", self._seq_fps)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Videos…")
        btn_add.clicked.connect(self._add_videos)
        btn_row.addWidget(btn_add)
        btn_seq = QPushButton("Add PNG Sequences…")
        btn_seq.setToolTip("Pick a folder of sequentially named images (one "
                           "video), or a folder whose subfolders each hold a "
                           "sequence (one video per subfolder).")
        btn_seq.clicked.connect(self._add_sequences)
        btn_row.addWidget(btn_seq)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._file_list = QListWidget()
        layout.addWidget(self._file_list)

        self._lbl_status = QLabel("Add videos or PNG sequences, then press Import.")
        layout.addWidget(self._lbl_status)
        self._progress = QProgressBar()
        layout.addWidget(self._progress)

        buttons = QDialogButtonBox()
        self._btn_import = QPushButton("Import && Extract")
        self._btn_import.setDefault(True)
        self._btn_import.clicked.connect(self._start)
        buttons.addButton(self._btn_import, QDialogButtonBox.AcceptRole)
        self._btn_close = buttons.addButton(QDialogButtonBox.Close)
        buttons.rejected.connect(self._on_close)
        layout.addWidget(buttons)

    # ---- setup ----

    def _add_item(self, item: dict):
        if any(i["path"] == item["path"] for i in self._items):
            return
        self._items.append(item)
        self._file_list.addItem(item["label"])

    def _add_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Videos", "", VIDEO_FILTER)
        for p in paths:
            self._add_item({"type": "video", "path": p, "label": Path(p).name})
        self._update_count()

    def _add_sequences(self):
        folder = QFileDialog.getExistingDirectory(self, "Select PNG Sequence Folder")
        if not folder:
            return
        sequences = find_sequences(folder)
        if not sequences:
            QMessageBox.warning(
                self, "No Sequences",
                "No image frames found in that folder or its subfolders.")
            return
        for seq in sequences:
            n = len(list_sequence(seq))
            self._add_item({
                "type": "sequence", "path": str(seq),
                "label": f"{seq.name}/  ({n} frames)",
            })
        self._update_count()

    def _update_count(self):
        videos = sum(1 for i in self._items if i["type"] == "video")
        seqs = len(self._items) - videos
        self._lbl_status.setText(
            f"{videos} video(s) + {seqs} sequence(s) queued.")

    def _clear(self):
        self._items.clear()
        self._file_list.clear()
        self._lbl_status.setText("Add videos or PNG sequences, then press Import.")

    # ---- import & extraction chain ----

    def _start(self):
        if not self._items:
            QMessageBox.warning(self, "Nothing Queued",
                                "Add video files or PNG sequences first.")
            return
        if self._participant.currentIndex() < 0:
            QMessageBox.warning(self, "No Participant",
                                "Create a participant first (Home → New Participant).")
            return

        p_id = self._participant.currentData()
        self._p_code = get_participant(p_id)["participant_code"]
        dataset = self._dataset.currentText()
        hand = self._hand.currentText()
        dominant = hand if hand in ("right", "left") else "right"

        self._queue = []
        for item in self._items:
            session_id = add_session(
                p_id, lighting="normal", background="plain",
                dominant_hand=dominant,
                notes=f"bulk import: {Path(item['path']).name}",
                dataset=dataset,
            )
            self._queue.append((session_id, item))

        self._current = 0
        self._imported = []
        self._errors = []
        self._cancelled = False
        self._set_running(True)
        self._next()

    def _set_running(self, running: bool):
        self._btn_import.setEnabled(not running)
        for w in (self._dataset, self._participant, self._hand, self._seq_fps):
            w.setEnabled(not running)

    def _session_dir(self, session_id: int) -> Path:
        out_dir = DATA_DIR / self._p_code / f"S{session_id:03d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir

    def _next(self):
        if self._cancelled or self._current >= len(self._queue):
            self._finish()
            return
        session_id, item = self._queue[self._current]
        pos = f"{self._current + 1}/{len(self._queue)}"
        out_dir = self._session_dir(session_id)

        if item["type"] == "sequence":
            self._lbl_status.setText(f"Converting {pos} ({item['label']})…")
            dest = str(out_dir / "video.mp4")
            self._converter = SequenceConverterThread(
                item["path"], dest, float(self._seq_fps.value()))
            self._converter.progress.connect(self._on_progress)
            self._converter.finished.connect(
                lambda path, sid=session_id: self._on_converted(sid, path))
            self._converter.error.connect(
                lambda msg, sid=session_id: self._on_one_error(sid, msg))
            self._converter.start()
        else:
            src = item["path"]
            suffix = Path(src).suffix.lower() or ".mp4"
            dest = str(out_dir / f"video{suffix}")
            shutil.copy2(src, dest)
            self._begin_extraction(session_id, dest)

    def _on_converted(self, session_id: int, video_path: str):
        self._begin_extraction(session_id, video_path)

    def _begin_extraction(self, session_id: int, video_path: str):
        update_session(session_id, status="recorded", video_path=video_path)
        pos = f"{self._current + 1}/{len(self._queue)}"
        self._lbl_status.setText(
            f"Extracting {pos} (S{session_id:03d})…")
        out_csv = str(self._session_dir(session_id) / "landmarks.csv")
        self._worker = ExtractorThread(
            video_path, out_csv,
            confidence_threshold=self._config.confidence_threshold,
            target_hand=self._hand.currentText(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.quality_ready.connect(
            lambda report, sid=session_id: save_quality_report(sid, report))
        self._worker.finished.connect(
            lambda csv_path, sid=session_id: self._on_one_done(sid, csv_path))
        self._worker.error.connect(
            lambda msg, sid=session_id: self._on_one_error(sid, msg))
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(current)

    def _on_one_done(self, session_id: int, csv_path: str):
        update_session(session_id, landmarks_path=csv_path, status="processed")
        self._imported.append(session_id)
        self._current += 1
        self._next()

    def _on_one_error(self, session_id: int, msg: str):
        self._errors.append(f"Session {session_id}: {msg}")
        self._current += 1
        self._next()

    def _finish(self):
        self._set_running(False)
        summary = (f"Imported {len(self._imported)} session(s) into "
                   f"'{self._dataset.currentText()}'.")
        if self._errors:
            summary += "\n\nErrors:\n" + "\n".join(self._errors)
        if self._cancelled:
            summary += "\n(cancelled before finishing the queue)"
        self._lbl_status.setText("Done. Annotate each session via Open Session.")
        QMessageBox.information(self, "Bulk Import", summary)
        self._clear()

    def _on_close(self):
        busy = (self._worker and self._worker.isRunning()) or (
            self._converter and self._converter.isRunning())
        if busy:
            self._cancelled = True
            self._lbl_status.setText("Finishing current item, then stopping…")
            return
        self.reject()
