import os
import sqlite3

from werkzeug.security import generate_password_hash

# Path to the SQLite database file in the project root.
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "spendly.db")


def get_db() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables if they do not exist. Safe to call repeatedly."""
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL    NOT NULL,
                category    TEXT    NOT NULL,
                date        TEXT    NOT NULL,           -- YYYY-MM-DD
                description TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db() -> None:
    """Insert the demo user and 8 sample expenses, but only once."""
    conn = get_db()
    try:
        cur = conn.cursor()

        # Idempotency guard — bail out if anything is already seeded.
        cur.execute("SELECT COUNT(*) AS n FROM users")
        if cur.fetchone()["n"] > 0:
            return

        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (
                "Demo User",
                "demo@spendly.com",
                generate_password_hash("demo123"),
            ),
        )
        user_id = cur.lastrowid

        # 8 sample expenses for June 2026 (today is 2026-06-23).
        # Covers all 7 categories; Food repeats per spec (7 categories + 8 expenses).
        expenses = [
            # (amount, category, date, description)
            (450.00,  "Food",           "2026-06-02", "Groceries — weekly stock-up"),
            (180.50,  "Transport",      "2026-06-05", "Metro card top-up"),
            (2200.00, "Bills",          "2026-06-07", "Electricity bill"),
            (650.00,  "Health",         "2026-06-10", "Pharmacy — vitamins"),
            (1200.00, "Entertainment",  "2026-06-14", "Movie night with friends"),
            (3499.00, "Shopping",       "2026-06-18", "Running shoes"),
            (220.00,  "Food",           "2026-06-20", "Dinner — local restaurant"),
            (150.00,  "Other",          "2026-06-22", "Houseplant for desk"),
        ]

        cur.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, amt, cat, dt, desc) for (amt, cat, dt, desc) in expenses],
        )

        conn.commit()
    finally:
        conn.close()
