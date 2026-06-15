import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
DB_PATH = str(_DATA_DIR / "saga.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    conn = get_connection()
    with transaction(conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id       TEXT PRIMARY KEY,
                owner    TEXT NOT NULL,
                balance  REAL NOT NULL CHECK(balance >= 0)
            );

            CREATE TABLE IF NOT EXISTS sagas (
                id         TEXT PRIMARY KEY,
                type       TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'STARTED',
                payload    TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS saga_steps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                saga_id     TEXT NOT NULL REFERENCES sagas(id),
                step_name   TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'PENDING',
                result      TEXT,
                executed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS transfer_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                saga_id      TEXT NOT NULL,
                from_account TEXT NOT NULL,
                to_account   TEXT NOT NULL,
                amount       REAL NOT NULL,
                status       TEXT NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
    conn.close()


def seed_accounts() -> None:
    conn = get_connection()
    with transaction(conn):
        conn.executemany(
            "INSERT OR IGNORE INTO accounts (id, owner, balance) VALUES (?, ?, ?)",
            [
                ("ACC-001", "Alice", 1000.0),
                ("ACC-002", "Bob", 500.0),
                ("ACC-003", "Carol", 250.0),
            ],
        )
    conn.close()
    print("Seeded accounts: Alice=$1000  Bob=$500  Carol=$250")


def reset_db() -> None:
    """Drop and recreate all tables — useful for a clean demo run."""
    conn = get_connection()
    with transaction(conn):
        conn.executescript("""
            DROP TABLE IF EXISTS transfer_log;
            DROP TABLE IF EXISTS saga_steps;
            DROP TABLE IF EXISTS sagas;
            DROP TABLE IF EXISTS accounts;
        """)
    conn.close()
    init_db()
