"""Selecting the tracked hand from MediaPipe results.

MediaPipe reports handedness assuming a mirrored (selfie-view) image.
Frames from cv2.VideoCapture are unmirrored, so the label must be swapped:
a physical right hand is reported as "Left".
"""


def expected_label(target_hand: str) -> str:
    return "Left" if target_hand.lower() == "right" else "Right"


def select_hand(hand_landmarks, handedness, target_hand: str):
    """Pick the target hand from a detection result.

    Returns (landmarks, score) or None. When two hands are detected only an
    exact handedness match is accepted; a lone detected hand is accepted
    regardless of label, since handedness classification is noisy and a
    single hand in frame is almost always the active one.
    """
    if not hand_landmarks:
        return None

    label = expected_label(target_hand)
    candidates = list(zip(hand_landmarks, handedness))
    matches = [
        (lms, h[0].score)
        for lms, h in candidates
        if h and h[0].category_name == label
    ]
    if matches:
        return max(matches, key=lambda m: m[1])
    if len(candidates) == 1:
        lms, h = candidates[0]
        return (lms, h[0].score if h else 0.0)
    return None
