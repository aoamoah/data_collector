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
