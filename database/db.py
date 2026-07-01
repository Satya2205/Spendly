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


def _date_clause(date_from: str | None, date_to: str | None) -> tuple[str, list]:
    """Return the SQL fragment and params that bound an `expenses.date` range.

    `date_from` and `date_to` are inclusive `YYYY-MM-DD` strings. When both
    are provided, returns `(" AND date BETWEEN ? AND ?", [date_from, date_to])`.
    Otherwise returns `("", [])` so callers can concatenate unconditionally.
    Used by every query helper that supports optional date filtering.
    """
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", [date_from, date_to]
    return "", []


def get_summary_stats(
    conn: sqlite3.Connection,
    user_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Aggregate spending stats for one user. Read-only.

    Returns a dict with:
        total_count   -- number of expenses in the active range
        total_amount  -- sum of expense amounts in the active range (float)
        month_amount  -- sum of expenses in the current calendar month (float);
                         unaffected by the active filter — it's a reference
                         value, not a filtered aggregate
        top_category  -- category with the highest total spend in the active
                         range, or None when the range is empty

    When `date_from` and `date_to` are both None, behaviour is identical to
    the original `get_user_stats` (unfiltered, all-time).
    """
    cur = conn.cursor()
    clause, params = _date_clause(date_from, date_to)

    cur.execute(
        f"SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?{clause}",
        (user_id, *params),
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
        f"SELECT COALESCE(SUM(amount), 0) AS s FROM expenses "
        f"WHERE user_id = ?{clause}",
        (user_id, *params),
    )
    total_amount = cur.fetchone()["s"]

    # `month_amount` is a reference value (current calendar month, unfiltered).
    ym = date.today().strftime("%Y-%m")
    cur.execute(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM expenses "
        "WHERE user_id = ? AND substr(date, 1, 7) = ?",
        (user_id, ym),
    )
    month_amount = cur.fetchone()["s"]

    cur.execute(
        f"SELECT category FROM expenses WHERE user_id = ?{clause} "
        f"GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        (user_id, *params),
    )
    row = cur.fetchone()
    top_category = row["category"] if row else None

    return {
        "total_count": total_count,
        "total_amount": float(total_amount),
        "month_amount": float(month_amount),
        "top_category": top_category,
    }


def get_recent_transactions(
    conn: sqlite3.Connection,
    user_id: int,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[sqlite3.Row]:
    """Return the most-recent expenses for one user, newest first.

    Ordered by date DESC, then id DESC (stable tiebreaker for same-day rows).
    Honours the optional date range. Returns an empty list when no rows match.
    The caller owns the connection's lifetime.
    """
    clause, params = _date_clause(date_from, date_to)
    cur = conn.execute(
        f"SELECT id, amount, category, date, description FROM expenses "
        f"WHERE user_id = ?{clause} "
        f"ORDER BY date DESC, id DESC LIMIT ?",
        (user_id, *params, limit),
    )
    return cur.fetchall()


def get_category_breakdown(
    conn: sqlite3.Connection,
    user_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[sqlite3.Row]:
    """Return per-category totals for one user, highest spend first.

    Each row has `category`, `total`, and `n` columns. Percentages are
    computed by the caller against the row with the largest `total`.
    Returns an empty list when the range is empty.
    """
    clause, params = _date_clause(date_from, date_to)
    cur = conn.execute(
        f"SELECT category, SUM(amount) AS total, COUNT(*) AS n "
        f"FROM expenses WHERE user_id = ?{clause} "
        f"GROUP BY category ORDER BY total DESC",
        (user_id, *params),
    )
    return cur.fetchall()


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
