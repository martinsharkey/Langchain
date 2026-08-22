import sqlite3


def connect(db_path: str, timeout: int = 30):
    """Open a WAL-mode SQLite connection with a generous timeout."""
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
