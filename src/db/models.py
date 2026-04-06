from datetime import datetime
from .database import get_connection


# ---------- Participants ----------

def add_participant(code: str, handedness: str, age_range: str, notes: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO participants (participant_code, handedness, age_range, notes) VALUES (?, ?, ?, ?)",
            (code, handedness, age_range, notes),
        )
        return cur.lastrowid


def get_all_participants() -> list:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM participants ORDER BY id").fetchall()


def get_participant(participant_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()


# ---------- Sessions ----------

def add_session(participant_id: int, lighting: str, background: str, dominant_hand: str) -> int:
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO sessions
               (participant_id, date_created, lighting, background, dominant_hand, status)
               VALUES (?, ?, ?, ?, ?, 'created')""",
            (participant_id, now, lighting, background, dominant_hand),
        )
        return cur.lastrowid


def get_session(session_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()


def get_sessions_for_participant(participant_id: int) -> list:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE participant_id = ? ORDER BY id",
            (participant_id,),
        ).fetchall()


def update_session(session_id: int, **kwargs):
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [session_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE sessions SET {fields} WHERE id = ?", values)


# ---------- Annotations ----------

def add_annotation(session_id: int, start_frame: int, end_frame: int, label: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO annotations (session_id, start_frame, end_frame, label) VALUES (?, ?, ?, ?)",
            (session_id, start_frame, end_frame, label),
        )
        return cur.lastrowid


def get_annotations_for_session(session_id: int) -> list:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM annotations WHERE session_id = ? ORDER BY start_frame",
            (session_id,),
        ).fetchall()


def delete_annotations_for_session(session_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM annotations WHERE session_id = ?", (session_id,))


def delete_annotation(annotation_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
