"""One-off script: seed a single realistic Indian user into the users table.

Uses the same get_db() pattern as database/db.py. Regenerates the email until
it is unique within the users table.
"""

import random
from datetime import datetime

from werkzeug.security import generate_password_hash

from database.db import get_db


# Realistic Indian names sampled across regions (North, South, East, West).
FIRST_NAMES = [
    # North
    "Rahul", "Aditya", "Ananya", "Priya", "Arjun", "Ishaan", "Kabir", "Neha",
    "Vikram", "Riya", "Aarav", "Sanya",
    # South
    "Karthik", "Lakshmi", "Divya", "Aravind", "Meera", "Suresh", "Anjali",
    "Harish", "Padma", "Vignesh",
    # East
    "Soumya", "Rohan", "Ishita", "Debjit", "Anirban", "Sneha",
    # West
    "Aditi", "Tanvi", "Rohit", "Kunal", "Pooja", "Nikhil",
]

LAST_NAMES = [
    # North
    "Sharma", "Verma", "Gupta", "Singh", "Kapoor", "Malhotra", "Chopra",
    "Bhatia", "Aggarwal",
    # South
    "Iyer", "Nair", "Reddy", "Rao", "Menon", "Pillai", "Krishnan", "Naidu",
    # East
    "Banerjee", "Chatterjee", "Mukherjee", "Das", "Bose", "Ghosh",
    # West
    "Patel", "Shah", "Desai", "Joshi", "Mehta", "Kulkarni", "Deshpande",
]

EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]


def generate_user() -> dict:
    """Build a fresh random user dict — name, email, plain password, created_at."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    name = f"{first} {last}"

    suffix = random.randint(10, 999)
    domain = random.choice(EMAIL_DOMAINS)
    email = f"{first.lower()}.{last.lower()}{suffix}@{domain}"

    return {
        "name": name,
        "email": email,
        "password": "password123",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def email_exists(conn, email: str) -> bool:
    """Return True if the email is already in the users table."""
    cur = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,))
    return cur.fetchone() is not None


def main() -> None:
    conn = get_db()
    try:
        # Regenerate until the email is unique.
        user = generate_user()
        while email_exists(conn, user["email"]):
            user = generate_user()

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                user["name"],
                user["email"],
                generate_password_hash(user["password"]),
                user["created_at"],
            ),
        )
        conn.commit()
        new_id = cur.lastrowid

        print("User seeded successfully:")
        print(f"  id:    {new_id}")
        print(f"  name:  {user['name']}")
        print(f"  email: {user['email']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
