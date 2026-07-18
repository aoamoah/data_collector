# AirWrite Capture – Agent Workflow

This project uses a 3-agent development system:

- Developer
- Tester
- Reviewer

Each agent has strict responsibilities.

---

## 1. Developer Agent

### Responsibilities

- Implement all modules:
  - Capture
  - Task Guide
  - Processing
  - Annotation
  - Export

- Use:
  - Python
  - PySide6
  - OpenCV
  - MediaPipe

- Follow:
  - `claude.md` strictly
  - modular architecture
  - clean code practices

### Rules

- No unnecessary frameworks
- No cloud features
- Keep everything local
- Ensure code readability
- Separate logic into modules

---

## 2. Tester Agent

### Responsibilities

Write and run:

#### Unit Tests
- Camera initialization
- Video recording
- File saving
- CSV generation
- SQLite operations

#### Integration Tests
- Record → Process → Annotate → Export flow
- Video → MediaPipe → CSV correctness
- Annotation → label consistency

#### Edge Case Testing
- No hand detected
- Low lighting
- Fast motion
- Partial occlusion
- Empty recordings

---

### Test Tools

- pytest
- mock for webcam inputs
- sample video files

---

## 3. Reviewer Agent

### Responsibilities

- Ensure `claude.md` is followed strictly
- Validate architecture decisions
- Check for:
  - unnecessary complexity
  - bugs
  - poor structure
  - incorrect data formats

### Enforce

- Simplicity
- Correct module separation
- Clean data pipeline
- No overengineering

---

## Collaboration Flow

1. Developer writes feature
2. Tester validates feature
3. Reviewer approves or rejects

If rejected:
- Developer fixes
- Cycle repeats

---

## Key Principles

### 1. Keep it simple
This is a local desktop app, not a distributed system.

### 2. Data quality > fancy features
The dataset is the product.

### 3. Reproducibility
Outputs must always be consistent.

### 4. Stability
App must not crash during recording or annotation.

---

## Definition of Success

The system is successful when:

- Sessions can be recorded reliably
- Landmarks are extracted correctly
- Labels are accurate
- Dataset is ready for ML training
