from dataclasses import dataclass, field

# Default durations in seconds, matching TASK_STEPS order in guide.py
DEFAULT_TASK_DURATIONS = [5, 3, 10, 3, 10, 5, 3]


@dataclass
class AppConfig:
    confidence_threshold: float = 0.5
    resolution: tuple = (640, 480)
    fps: int = 30
    task_durations: list = field(default_factory=lambda: list(DEFAULT_TASK_DURATIONS))
    audio_cues: bool = True
