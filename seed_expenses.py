"""One-off script: seed <count> realistic INR expenses for <user_id>,
spread across the past <months> months.

Uses the same get_db() pattern as database/db.py — no hardcoded DB path,
parameterised queries only, single transaction with rollback on failure.
"""

import random
import sys
from datetime import date, timedelta

from database.db import get_db


# Per-category (amount_min, amount_max) in INR and pool of realistic descriptions.
CATEGORIES = {
    "Food": (
        50, 800,
        [
            "Groceries — weekly stock-up",
            "Chai and samosa at tapri",
            "Lunch — office canteen",
            "Dinner at a local restaurant",
            "Swiggy order",
            "Zomato order",
            "Bread, milk, and eggs",
            "Street food — pav bhaji",
            "Filter coffee and idli",
            "Weekly sabzi-mandi haul",
        ],
    ),
    "Transport": (
        20, 500,
        [
            "Metro card top-up",
            "Uber to office",
            "Ola auto to station",
            "Petrol — two-wheeler",
            "Rapido bike ride",
            "Auto rickshaw fare",
            "State transport bus ticket",
            "Cab to airport",
        ],
    ),
    "Bills": (
        200, 3000,
        [
            "Electricity bill",
            "Broadband recharge",
            "Mobile postpaid bill",
            "DTH recharge",
            "Gas cylinder refill",
            "Water tanker",
            "Society maintenance",
            "Credit card bill — partial",
        ],
    ),
    "Health": (
        100, 2000,
        [
            "Pharmacy — vitamins",
            "Doctor consultation",
            "Lab tests",
            "Dental cleaning",
            "Gym monthly fee",
            "Yoga class drop-in",
            "First-aid supplies",
        ],
    ),
    "Entertainment": (
        100, 1500,
        [
            "Movie night — PVR",
            "OTT subscription renewal",
            "Bookstore haul",
            "Concert tickets",
            "Stand-up show",
            "Cafe with friends",
        ],
    ),
    "Shopping": (
        200, 5000,
        [
            "Running shoes",
            "Casual shirt",
            "Kitchen utensil set",
            "Phone cover and tempered glass",
            "Diwali gifts",
            "Earphones",
            "Festival clothing",
            "Online order — Amazon",
        ],
    ),
    "Other": (
        50, 1000,
        [
            "Houseplant for desk",
            "Barber visit",
            "Courier parcel",
            "Donation at temple",
            "Bank charges",
            "Stationery",
        ],
    ),
}

# Weighted distribution: Food most common, Health and Entertainment least.
CATEGORY_WEIGHTS = {
    "Food":           30,
    "Transport":      20,
    "Bills":          15,
    "Shopping":       12,
    "Other":          10,
    "Entertainment":   7,
    "Health":          6,
}
CATEGORY_NAMES = list(CATEGORY_WEIGHTS.keys())
CATEGORY_WEIGHT_LIST = [CATEGORY_WEIGHTS[c] for c in CATEGORY_NAMES]


def user_exists(conn, user_id: int) -> bool:
    """Return True iff a row with this id exists in the users table."""
    cur = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
    return cur.fetchone() is not None


def random_date_in_last_n_months(months: int, today: date) -> date:
    """Return a random date in (today - months, today]."""
    start = today - timedelta(days=months * 30)
    span = (today - start).days
    return start + timedelta(days=random.randint(0, span))


def generate_expenses(user_id: int, count: int, months: int, today: date) -> list[tuple]:
    """Build `count` (amount, category, date, description) tuples for user_id."""
    rows = []
    for _ in range(count):
        category = random.choices(CATEGORY_NAMES, weights=CATEGORY_WEIGHT_LIST, k=1)[0]
        lo, hi, descriptions = CATEGORIES[category]
        amount = round(random.uniform(lo, hi), 2)
        desc = random.choice(descriptions)
        d = random_date_in_last_n_months(months, today)
        rows.append((user_id, amount, category, d.isoformat(), desc))
    return rows


def main() -> int:
    # Step 1 — parse arguments.
    if len(sys.argv) != 4:
        print("Usage: /seed-expenses <user_id> <count> <months>")
        print("Example: /seed-expenses 1 50 6")
        return 1
    try:
        user_id = int(sys.argv[1])
        count = int(sys.argv[2])
        months = int(sys.argv[3])
    except ValueError:
        print("Usage: /seed-expenses <user_id> <count> <months>")
        print("Example: /seed-expenses 1 50 6")
        return 1

    today = date.today()

    conn = get_db()
    try:
        # Step 2 — verify the user exists.
        if not user_exists(conn, user_id):
            print(f"No user found with id {user_id}.")
            return 1

        # Step 3 — generate and insert in a single transaction.
        rows = generate_expenses(user_id, count, months, today)
        try:
            conn.execute("BEGIN")
            conn.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Step 4 — report.
        dates = [r[3] for r in rows]
        print(f"Inserted {len(rows)} expenses for user {user_id}.")
        print(f"Date range: {min(dates)}  to  {max(dates)}")
        print("Sample of 5 inserted records:")
        for r in rows[:5]:
            print(f"  ₹{r[1]:>7.2f}  {r[2]:<14}  {r[3]}  {r[4]}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
