from dataclasses import dataclass


@dataclass
class FrameQuality:
    frame_index: int
    timestamp_ms: int
    confidence: float
    hand_detected: bool
    is_duplicate: bool = False


def compute_quality_report(frame_qualities: list[FrameQuality]) -> dict:
    if not frame_qualities:
        return {}
    total = len(frame_qualities)
    duplicates = sum(1 for f in frame_qualities if f.is_duplicate)
    valid = [f for f in frame_qualities if not f.is_duplicate]
    with_hand = sum(1 for f in valid if f.hand_detected)
    confidences = [f.confidence for f in valid if f.hand_detected]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "total_frames": total,
        "frames_with_hand": with_hand,
        "pct_detected": round(100 * with_hand / total, 1) if total > 0 else 0.0,
        "avg_confidence": round(avg_conf, 4),
        "duplicate_frames": duplicates,
    }
