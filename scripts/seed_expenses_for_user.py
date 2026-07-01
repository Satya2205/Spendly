"""Seed 10 realistic expenses for user_id=3 across the past 6 months.

Reads schema/connection pattern from database/db.py — never hardcodes the
DB filename. Uses parameterised queries and a single transaction.
"""
import random
from datetime import date, timedelta

from database.db import get_db

USER_ID = 3
COUNT = 10
MONTHS = 6

CATEGORIES = [
    # (name, amount_min, amount_max, weight, sample descriptions)
    ("Food",         50,  800, 4, [
        "Groceries — weekly stock-up", "Lunch — local thali",
        "Dinner — restaurant", "Tea and snacks", "Sunday biryani",
    ]),
    ("Transport",    20,  500, 3, [
        "Metro card top-up", "Auto rickshaw", "Rapido ride",
        "Petrol refill", "Ola to airport",
    ]),
    ("Bills",       200, 3000, 2, [
        "Electricity bill", "Broadband bill", "Mobile recharge",
        "Gas cylinder", "Water bill",
    ]),
    ("Health",      100, 2000, 1, [
        "Pharmacy — vitamins", "Doctor consultation", "Lab tests",
    ]),
    ("Entertainment", 100, 1500, 1, [
        "Movie night with friends", "Netflix subscription",
        "Concert ticket", "Bookstore haul",
    ]),
    ("Shopping",    200, 5000, 2, [
        "Running shoes", "Winter jacket", "Phone case",
        "Kitchen appliance", "Festival gift",
    ]),
    ("Other",        50, 1000, 2, [
        "Houseplant for desk", "Charity donation", "Stationery",
        "Salon visit", "Home repairs",
    ]),
]


def random_date_within_last_n_months(today: date, n: int) -> date:
    """Pick a random day somewhere in the past `n` calendar months, inclusive."""
    # Earliest allowed date = first day of (today.month - n + 1).
    # Latest allowed date = today.
    days_back = random.randint(0, n * 31)
    return today - timedelta(days=days_back)


def main() -> None:
    today = date.today()
    pool = []
    for _name, lo, hi, weight, descs in CATEGORIES:
        pool.extend([(lo, hi, descs)] * weight)

    rows = []
    for _ in range(COUNT):
        lo, hi, descs = random.choice(pool)
        amount = round(random.uniform(lo, hi), 2)
        cat_name = next(n for n, a, b, w, d in CATEGORIES if (a, b, d) == (lo, hi, descs))
        rows.append((
            USER_ID,
            amount,
            cat_name,
            random_date_within_last_n_months(today, MONTHS).isoformat(),
            random.choice(descs),
        ))

    conn = get_db()
    try:
        # Single transaction — rolls back the whole batch on any failure.
        try:
            conn.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Report
        sample = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (USER_ID,),
        ).fetchall()
        rng = conn.execute(
            "SELECT MIN(date) AS lo, MAX(date) AS hi, COUNT(*) AS n FROM expenses "
            "WHERE user_id = ?",
            (USER_ID,),
        ).fetchone()
    finally:
        conn.close()

    print(f"Inserted {len(rows)} expenses for user_id={USER_ID}.")
    print(f"Date range for this user: {rng['lo']}  to  {rng['hi']}  ({rng['n']} total)")
    print("Last 5 inserted:")
    for r in sample:
        print(f"  id={r['id']:>3}  {r['date']}  {r['category']:<14}  "
              f"₹{r['amount']:>8.2f}  — {r['description']}")


if __name__ == "__main__":
    random.seed(42)  # deterministic spread for reproducibility
    main()