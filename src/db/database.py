import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent.parent.parent / "data_collector.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_code TEXT UNIQUE NOT NULL,
                handedness TEXT,
                age_range TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id INTEGER NOT NULL REFERENCES participants(id),
                date_created TEXT NOT NULL,
                lighting TEXT,
                background TEXT,
                dominant_hand TEXT,
                video_path TEXT,
                landmarks_path TEXT,
                labels_path TEXT,
                status TEXT DEFAULT 'created'
            );

            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES sessions(id),
                start_frame INTEGER NOT NULL,
                end_frame INTEGER NOT NULL,
                label TEXT NOT NULL
            );
        """)
