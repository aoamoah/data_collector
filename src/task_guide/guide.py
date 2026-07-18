import sys

from PySide6.QtCore import QObject, QTimer, Signal


TASK_STEPS = [
    ("Rest",    "Rest your hand in your lap or on the desk.",        5),
    ("Prepare", "Raise your hand to writing position.",               3),
    ("Write",   "Write a letter or word in the air.",                10),
    ("Pause",   "Hold your hand still — pause mid-writing.",          3),
    ("Resume",  "Continue writing in the air.",                      10),
    ("Gesture", "Make a non-writing gesture (e.g. wave or point).",   5),
    ("Return",  "Lower your hand and return to rest.",                3),
]


class TaskGuide(QObject):
    step_changed = Signal(int, str, str, int)   # index, name, instruction, total_seconds
    tick = Signal(int, int)                     # step_index, remaining_seconds
    completed = Signal()

    def __init__(self, parent=None, durations: list[int] | None = None, audio_cues: bool = True):
        super().__init__(parent)
        self._durations = durations if durations else [d for _, _, d in TASK_STEPS]
        self._audio_cues = audio_cues
        self._step = 0
        self._remaining = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def start(self):
        self._step = 0
        self._emit_step()
        self._timer.start()

    def skip(self):
        self._advance()

    def stop(self):
        self._timer.stop()

    def _emit_step(self):
        name, instruction, _ = TASK_STEPS[self._step]
        self._remaining = self._durations[self._step]
        self.step_changed.emit(self._step, name, instruction, self._remaining)
        self.tick.emit(self._step, self._remaining)
        if self._audio_cues:
            self._beep()

    def _on_tick(self):
        self._remaining -= 1
        self.tick.emit(self._step, self._remaining)
        if self._remaining <= 0:
            self._advance()

    def _advance(self):
        self._step += 1
        if self._step >= len(TASK_STEPS):
            self._timer.stop()
            if self._audio_cues:
                self._beep(finish=True)
            self.completed.emit()
        else:
            self._emit_step()

    def _beep(self, finish: bool = False):
        try:
            if sys.platform == "win32":
                import winsound
                if finish:
                    winsound.Beep(1200, 300)
                    winsound.Beep(1400, 300)
                else:
                    winsound.Beep(1000, 150)
            else:
                from PySide6.QtWidgets import QApplication
                QApplication.beep()
                if finish:
                    QApplication.beep()
        except Exception:
            pass
