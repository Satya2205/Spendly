import os
import re
import sqlite3
from datetime import date, datetime

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database.db import (
    create_user,
    get_category_breakdown,
    get_db,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)

# Sessions are used to keep the user signed in after registration/login.
# In production, set the SECRET_KEY env var to a long random value.
# This dev fallback is intentionally weak and must never be used in production.
app.secret_key = os.environ.get("SECRET_KEY") or "dev-only-spendly-secret-change-me"

# Compiled once at import time. Requires: non-empty local part, '@', non-empty
# domain, '.', non-empty TLD; no whitespace anywhere.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ #
# Date-filter helpers — used only by the profile route                #
# ------------------------------------------------------------------ #
def _parse_iso_date(value: str | None) -> str | None:
    """Return the input as `YYYY-MM-DD` if it parses cleanly, else None.

    A `ValueError` from `datetime.strptime` falls through to None so that
    callers can treat a malformed query param as "absent" and silently
    fall back to the unfiltered view.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _month_start(d: date, months_back: int) -> date:
    """First day of the month `months_back` calendar months before `d`.

    `months_back=0` returns the first of `d`'s own month; `months_back=2`
    with `d=2026-06-27` returns `2026-04-01`. Wraps across years without
    needing `dateutil`. Used by the "Last N months" preset buttons.
    """
    year = d.year
    month = d.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _build_presets(today: date) -> dict:
    """Return the four preset filter ranges keyed by display name.

    Each value is `(date_from, date_to)` as ISO strings, or `(None, None)`
    for the "All Time" preset (which must produce a clean `/profile` URL).
    """
    return {
        "All Time": (None, None),
        "This Month": (
            _month_start(today, 0).isoformat(),
            today.isoformat(),
        ),
        "Last 3 Months": (
            _month_start(today, 2).isoformat(),
            today.isoformat(),
        ),
        "Last 6 Months": (
            _month_start(today, 5).isoformat(),
            today.isoformat(),
        ),
    }


# ------------------------------------------------------------------ #
# Database — initialize schema and seed demo data on startup          #
# ------------------------------------------------------------------ #
with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        # --- validation ---
        if not name or len(name) > 80:
            flash("Please enter your name (max 80 characters).", "error")
        elif not EMAIL_RE.match(email):
            flash("Please enter a valid email address.", "error")
        elif len(password) < 8 or not password.strip():
            flash("Password must be at least 8 characters.", "error")
        else:
            # --- insert + sign in ---
            conn = get_db()
            try:
                try:
                    user_id = create_user(conn, name, email, password)
                except sqlite3.IntegrityError:
                    flash("Email already registered", "error")
                else:
                    session.clear()
                    session["user_id"] = user_id
                    session["user_name"] = name
                    flash("Account created — welcome to Spendly!", "success")
                    return redirect(url_for("profile"))
            finally:
                conn.close()

    return render_template("register.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        flash("Please sign in to view analytics.", "error")
        return redirect(url_for("login"))
    return render_template("analytics.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please sign in to view your profile.", "error")
        return redirect(url_for("login"))

    # --- date filter: parse + validate query params ---
    raw_from = request.args.get("date_from")
    raw_to = request.args.get("date_to")
    date_from = _parse_iso_date(raw_from)
    date_to = _parse_iso_date(raw_to)

    # If only one bound is present, ignore the filter entirely (we need
    # both ends to apply a meaningful BETWEEN). This also protects against
    # the `date_from > date_to` inversion case below.
    if (date_from is None) != (date_to is None):
        date_from = None
        date_to = None

    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = None
        date_to = None

    today = date.today()
    presets = _build_presets(today)

    # Identify which preset (if any) the active filter matches exactly, so
    # the template can highlight its button without comparing strings.
    active_preset = None
    for name, (p_from, p_to) in presets.items():
        if p_from == date_from and p_to == date_to:
            active_preset = name
            break

    conn = get_db()
    try:
        user = get_user_by_id(conn, user_id)
        if user is None:
            # Stale session pointing at a user that no longer exists.
            session.clear()
            flash("Your session has expired. Please sign in again.", "error")
            return redirect(url_for("login"))

        stats = get_summary_stats(conn, user_id, date_from, date_to)
        transactions = get_recent_transactions(
            conn, user_id, limit=10, date_from=date_from, date_to=date_to
        )
        breakdown_rows = get_category_breakdown(conn, user_id, date_from, date_to)

        # Percentages for the category breakdown are computed here so the
        # template stays free of business logic.
        max_total = float(breakdown_rows[0]["total"]) if breakdown_rows else 0.0
        breakdown = [
            {
                "category": row["category"],
                "total": float(row["total"]),
                "n": row["n"],
                "pct": (float(row["total"]) / max_total * 100.0) if max_total else 0.0,
            }
            for row in breakdown_rows
        ]
    finally:
        conn.close()

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        breakdown=breakdown,
        date_from=date_from or "",
        date_to=date_to or "",
        presets=presets,
        active_preset=active_preset,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
