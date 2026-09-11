import sqlite3


def get_schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _set_schema_version(conn: sqlite3.Connection, version: int):
    conn.execute(f"PRAGMA user_version = {version}")


def run_migrations(conn: sqlite3.Connection):
    version = get_schema_version(conn)

    if version < 1:
        conn.execute("ALTER TABLE sessions ADD COLUMN notes TEXT DEFAULT ''")
        conn.execute("ALTER TABLE sessions ADD COLUMN flagged INTEGER DEFAULT 0")
        conn.commit()
        _set_schema_version(conn, 1)

    if version < 2:
        conn.execute("ALTER TABLE sessions ADD COLUMN quality_report TEXT DEFAULT NULL")
        conn.commit()
        _set_schema_version(conn, 2)

    if version < 3:
        # Which dataset collection the session belongs to (its export target):
        # dataset (own recordings), dataset_WITA, dataset_IPN
        conn.execute("ALTER TABLE sessions ADD COLUMN dataset TEXT DEFAULT 'dataset'")
        conn.commit()
        _set_schema_version(conn, 3)

    if version < 4:
        # The file a session's video was imported from. With several external
        # sources, provenance has to survive into the export — the session
        # notes were the only record of it
        conn.execute("ALTER TABLE sessions ADD COLUMN source_path TEXT DEFAULT NULL")
        conn.commit()
        _set_schema_version(conn, 4)
