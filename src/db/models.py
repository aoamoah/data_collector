import json
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


def delete_participant(participant_id: int):
    """Delete participant and cascade-delete all their sessions and annotations."""
    with get_connection() as conn:
        sessions = conn.execute(
            "SELECT id FROM sessions WHERE participant_id = ?", (participant_id,)
        ).fetchall()
        for s in sessions:
            conn.execute("DELETE FROM annotations WHERE session_id = ?", (s["id"],))
        conn.execute("DELETE FROM sessions WHERE participant_id = ?", (participant_id,))
        conn.execute("DELETE FROM participants WHERE id = ?", (participant_id,))


# ---------- Sessions ----------

def add_session(
    participant_id: int,
    lighting: str,
    background: str,
    dominant_hand: str,
    notes: str = "",
    dataset: str = "dataset",
) -> int:
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO sessions
               (participant_id, date_created, lighting, background, dominant_hand,
                notes, dataset, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'created')""",
            (participant_id, now, lighting, background, dominant_hand, notes, dataset),
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


def get_all_sessions() -> list:
    """Return all sessions joined with participant_code, ordered by participant then session."""
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.*, p.participant_code
               FROM sessions s
               JOIN participants p ON s.participant_id = p.id
               ORDER BY p.participant_code, s.id"""
        ).fetchall()


def update_session(session_id: int, **kwargs):
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [session_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE sessions SET {fields} WHERE id = ?", values)


def delete_session(session_id: int):
    """Delete session and its annotations from the DB."""
    with get_connection() as conn:
        conn.execute("DELETE FROM annotations WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def flag_session(session_id: int, flagged: bool):
    with get_connection() as conn:
        conn.execute("UPDATE sessions SET flagged = ? WHERE id = ?", (int(flagged), session_id))


def save_quality_report(session_id: int, report: dict):
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET quality_report = ? WHERE id = ?",
            (json.dumps(report), session_id),
        )


def get_quality_report(session_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT quality_report FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if row and row["quality_report"]:
        return json.loads(row["quality_report"])
    return None


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
