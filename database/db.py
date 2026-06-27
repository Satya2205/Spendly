import os
import sqlite3
from datetime import date

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


def create_user(conn: sqlite3.Connection, name: str, email: str, password: str) -> int:
    """Insert a new user with a werkzeug-hashed password. Returns the new id.

    Lets ``sqlite3.IntegrityError`` propagate so the caller can translate a
    UNIQUE-constraint violation on ``users.email`` into a friendly message.
    The caller owns the connection's lifetime and is responsible for closing it.
    """
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    """Fetch id, name, email, created_at for one user. Returns None if missing.

    Read-only. Caller owns the connection's lifetime.
    """
    cur = conn.execute(
        "SELECT id, name, email, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    return cur.fetchone()


def get_user_stats(conn: sqlite3.Connection, user_id: int) -> dict:
    """Aggregate spending stats for one user. Read-only.

    Returns a dict with:
        total_count   -- number of expenses
        total_amount  -- all-time sum of expense amounts (float, 0.0 if none)
        month_amount  -- sum of expenses in the current calendar month (float)
        top_category  -- category with the highest total spend, or None

    Early-returns a zeroed dict when the user has no expenses to keep
    the empty-state path simple for the caller.
    """
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?",
        (user_id,),
    )
    total_count = cur.fetchone()["n"]
    if total_count == 0:
        return {
            "total_count": 0,
            "total_amount": 0.0,
            "month_amount": 0.0,
            "top_category": None,
        }

    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM expenses WHERE user_id = ?",
        (user_id,),
    )
    total_amount = cur.fetchone()["s"]

    ym = date.today().strftime("%Y-%m")
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM expenses "
        "WHERE user_id = ? AND substr(date, 1, 7) = ?",
        (user_id, ym),
    )
    month_amount = cur.fetchone()["s"]

    cur.execute(
        "SELECT category FROM expenses WHERE user_id = ? "
        "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        (user_id,),
    )
    row = cur.fetchone()
    top_category = row["category"] if row else None

    return {
        "total_count": total_count,
        "total_amount": float(total_amount),
        "month_amount": float(month_amount),
        "top_category": top_category,
    }


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
