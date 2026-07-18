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

Structure:
- frame_index
- timestamp_ms
- hand_detected
- detection_confidence
- tracking_confidence
- l0_x, l0_y, l0_z ... l20_z

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
- not_writing

Optional internal states:
- rest
- prepare
- pause
- gesture

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

### metadata.json

```json
{
  "participant_id": "P001",
  "session_id": "S001",
  "lighting": "bright",
  "background": "plain",
  "dominant_hand": "right"
}
```

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
