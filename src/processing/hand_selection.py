"""Selecting the tracked hand from MediaPipe results.

Empirically verified on this project's own recordings (unmirrored
cv2.VideoCapture frames): the Tasks HandLandmarker labels the physical
right hand "Right" — the legacy MediaPipe docs' mirrored-image caveat
does not apply, so the mapping is identity.

Sources recorded on a phone's front camera are often mirrored, which swaps
the label. Choose "either" for those; the per-frame handedness label is
written to landmarks.csv so the flip can be detected and corrected later.
"""


def expected_label(target_hand: str) -> str:
    return "Right" if target_hand.lower() == "right" else "Left"


def select_hand_index(hand_landmarks, handedness, target_hand: str):
    """Pick the tracked hand from a detection result.

    target_hand "right"/"left" requires an exact (mirror-corrected)
    handedness match, so the choice genuinely filters which hand is kept.
    target_hand "either" keeps the highest-scoring hand — for ambidextrous
    sessions where the participant switched hands mid-video.
    Returns (index into the result lists, score, handedness label) or None.
    """
    if not hand_landmarks:
        return None

    candidates = [
        (i, h[0].score if h else 0.0, h[0].category_name if h else None)
        for i, h in enumerate(handedness[:len(hand_landmarks)])
    ]
    if target_hand.lower() != "either":
        label = expected_label(target_hand)
        candidates = [c for c in candidates if c[2] == label]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[1])


def select_hand(hand_landmarks, handedness, target_hand: str):
    """Returns (landmarks, score) of the tracked hand, or None."""
    picked = select_hand_index(hand_landmarks, handedness, target_hand)
    if picked is None:
        return None
    index, score, _ = picked
    return hand_landmarks[index], score
