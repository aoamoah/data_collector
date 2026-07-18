"""Selecting the tracked hand from MediaPipe results.

Empirically verified on this project's own recordings (unmirrored
cv2.VideoCapture frames): the Tasks HandLandmarker labels the physical
right hand "Right" — the legacy MediaPipe docs' mirrored-image caveat
does not apply, so the mapping is identity.
"""


def expected_label(target_hand: str) -> str:
    return "Right" if target_hand.lower() == "right" else "Left"


def select_hand(hand_landmarks, handedness, target_hand: str):
    """Pick the tracked hand from a detection result.

    target_hand "right"/"left" requires an exact (mirror-corrected)
    handedness match, so the choice genuinely filters which hand is kept.
    target_hand "either" keeps the highest-scoring hand — for ambidextrous
    sessions where the participant switched hands mid-video.
    Returns (landmarks, score) or None.
    """
    if not hand_landmarks:
        return None

    candidates = [
        (lms, h[0].score if h else 0.0, h[0].category_name if h else None)
        for lms, h in zip(hand_landmarks, handedness)
    ]

    if target_hand.lower() == "either":
        best = max(candidates, key=lambda c: c[1])
        return (best[0], best[1])

    label = expected_label(target_hand)
    matches = [(lms, score) for lms, score, name in candidates if name == label]
    if matches:
        return max(matches, key=lambda m: m[1])
    return None
