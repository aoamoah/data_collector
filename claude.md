# AirWrite Capture – Phase 1 Data Collection Desktop Application

## Overview

AirWrite Capture is a **local desktop application** designed to collect and annotate data for:

> Real-Time Writing State Detection for Continuous Air-Writing Using Hand Pose Classification

The system captures webcam video, extracts MediaPipe hand landmarks, allows annotation of writing vs non-writing states, and exports structured datasets for machine learning.

---

## Core Objectives

1. Record air-writing sessions using a webcam
2. Extract 21 hand landmarks (x, y, z) per frame using MediaPipe
3. Annotate writing vs not-writing states
4. Export clean, structured datasets (CSV + metadata)
5. Ensure reproducibility and consistency

---

## Tech Stack

### Language
- Python 3.10+

### UI
- PySide6 (Qt-based desktop UI)

### Computer Vision
- OpenCV
- MediaPipe Hands

### Storage
- SQLite (local database)
- CSV / JSON (dataset export)

---

## System Architecture

Single-process modular architecture:

```text
[ UI Layer ]
    ↓
[ Capture Module ]
    ↓
[ Processing Module ]
    ↓
[ Annotation Module ]
    ↓
[ Export Module ]
    ↓
[ SQLite DB + File Storage ]
```

---

## Modules

### 1. Capture Module

Responsibilities:
- Access webcam
- Display live preview
- Record video (MP4/WebM)
- Save locally

Features:
- Start/Stop recording
- Frame counter
- FPS display
- Camera validation

---

### 2. Task Guide Module

Responsibilities:
- Guide participant through tasks

Task flow:
1. Rest hand
2. Raise hand (preparation)
3. Write in air
4. Pause
5. Resume writing
6. Gesture (non-writing)
7. Return to rest

Features:
- Prompt display
- Countdown timers
- Step progression

---

### 3. Processing Module

Responsibilities:
- Load recorded video
- Run MediaPipe Hands
- Extract landmarks per frame

Output:
- `landmarks.csv`
- `annotation_proxy.mp4` — every decoded frame, re-encoded (≤960 px). Frame N
  of the proxy is row N of landmarks.csv, and it seeks exactly. OpenCV seeking
  on the source is not frame-exact on every container (IPN `.avi`: up to 14
  frames off), so the annotation screen always shows the proxy. Viewing aid
  only — never exported.
- The extraction report (DB `quality_report`): detection stats plus `video`
  (resolution, fps, header vs decoded frames), `timing` (source, repairs,
  measured fps) and `extraction` (MediaPipe version, model hash, running mode,
  thresholds, target hand, handedness counts).

Structure:
- frame_index
- timestamp_ms — real capture time when the recorder logged one
  (`capture_timestamps.csv`), else the container clock; always strictly
  increasing (a stalled clock is advanced one frame, not skipped)
- hand_detected
- detection_confidence
- tracking_confidence
- l0_x, l0_y, l0_z ... l20_z — image landmarks (x, y as fractions of width, height)
- handedness — MediaPipe Left/Right for the tracked hand
- wl0_x ... wl20_z — world landmarks, metres, hand-centred: independent of
  resolution and aspect ratio

---

### 4. Annotation Module

Responsibilities:
- Label writing vs not-writing

Features:
- Video playback
- Frame timeline
- Range selection
- Label assignment

Labels:
- writing
- not_writing — includes pauses inside a letter or word
- unsure — cannot be judged (blur, occlusion); excluded from training and scoring

The newest annotation overwrites whatever it overlaps, so a short pause can
be marked inside a longer writing range. The label timeline under the video
shows every frame's label; playback runs at 0.25×–2× for placing short-pause
boundaries. Unlabelled frames are saved as not_writing after a warning.

A labelling guide sits beside the video (F1 toggles it), and the rule for the
selected label shows under the controls. Its text lives in
`src/annotation/labelling_guide.py`. The rule is "fingertip as a pen on paper":
pen-down is writing; pauses and moves between strokes or letters are
not_writing. Change it only there, and before annotating, because sources
annotated under different rules can't be pooled.

---

### 5. Export Module

Responsibilities:
- Generate dataset files

Output structure:

```text
dataset/
  P001/
    S001/
      video.mp4     (extension follows the source container, e.g. video.avi)
      landmarks.csv
      labels.csv
      metadata.json
```

Session codes use the global session id (`S018`), not a per-participant
counter.

---

## Database Schema (SQLite)

### participants
- id
- participant_code
- handedness
- age_range
- notes

### sessions
- id
- participant_id
- date_created
- lighting
- background
- dominant_hand
- video_path
- landmarks_path
- labels_path
- status
- notes
- flagged
- quality_report (JSON, written after extraction)
- dataset (export folder)
- source_path (file the video was imported from)

Schema changes are applied via `src/db/migrations.py` using `PRAGMA user_version`.

### annotations
- id
- session_id
- start_frame
- end_frame
- label

---

## File Formats

### landmarks.csv

```csv
frame_index,timestamp_ms,hand_detected,detection_confidence,tracking_confidence,l0_x,l0_y,l0_z,...,l20_x,l20_y,l20_z
```

Note: MediaPipe's HandLandmarker only exposes a handedness classification
score per hand. Both `detection_confidence` and `tracking_confidence` contain
that score, kept as two columns for backward compatibility with existing
exports.

### labels.csv

```csv
frame_index,label
```

One row per landmarks.csv row. `label` is writing, not_writing or unsure.

### metadata.json (schema_version 2)

```json
{
  "schema_version": 2,
  "participant_id": "P001",
  "session_id": "S001",
  "dataset": "dataset",
  "source_file": null,
  "lighting": "bright",
  "background": "plain",
  "dominant_hand": "right",
  "video": {"width": 640, "height": 480, "fps": 30.0, "aspect": 1.333333,
            "header_frames": 1083, "decoded_frames": 1083, "fourcc": "FMP4"},
  "timing": {"source": "capture_log", "timestamp_repairs": 0, "measured_fps": 29.97},
  "extraction": {"mediapipe_version": "0.10.35", "running_mode": "VIDEO", "...": "..."},
  "detection": {"pct_detected": 81.9, "...": "..."},
  "landmark_columns": {"image": "...", "world": "...", "handedness": "...", "rows": 1083},
  "labels": {"set": ["writing", "not_writing", "unsure"],
             "excluded_from_training": ["unsure"], "counts": {"...": 0}}
}
```

The trainer reads the resolution from here; `scan_resolutions.py` is only
needed for exports made before schema_version 2.

### Datasets

Each session belongs to a dataset, which is its export folder: `dataset`
(own recordings) or `dataset_<Source>` for an external source. New names can
be typed in the New Session and Bulk Import forms (letters, digits, hyphens).

---

## UI Screens

1. Home
   - New Participant
   - New Session
   - Open Session

2. Participant Form

3. Recording Screen
   - Webcam preview
   - Task prompts
   - Record controls

4. Processing Screen
   - Extraction progress

5. Annotation Screen
   - Video player
   - Timeline
   - Label controls

---

## Workflow

1. Create participant
2. Start session
3. Record guided tasks
4. Run landmark extraction
5. Annotate frames
6. Export dataset

---

## Non-Functional Requirements

### Performance
- ≥30 FPS capture target
- Smooth playback

### Reliability
- Autosave session data
- Resume annotation

### Data Integrity
- Consistent naming
- No missing frames in export

---

## Constraints

- Runs entirely offline
- Single-user system
- No cloud or network dependencies

---

## Future Extensions (NOT Phase 1)

- Auto-label suggestions
- Real-time classification
- Multi-user support
- Cloud sync
- Dataset versioning

---

## Definition of Done

The system is complete when:
- You can record sessions reliably
- Landmarks are extracted correctly
- Labels can be applied easily
- Dataset exports are usable for ML training
