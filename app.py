import os
import re
import sqlite3

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from database.db import create_user, get_db, init_db, seed_db

app = Flask(__name__)

# Sessions are used to keep the user signed in after registration/login.
# In production, set the SECRET_KEY env var to a long random value.
# This dev fallback is intentionally weak and must never be used in production.
app.secret_key = os.environ.get("SECRET_KEY") or "dev-only-spendly-secret-change-me"

# Compiled once at import time. Requires: non-empty local part, '@', non-empty
# domain, '.', non-empty TLD; no whitespace anywhere.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
