# Spec: Registration

## Overview
Wire up the existing `/register` page so users can actually create an account. The GET half is already implemented (renders `register.html`); this step adds the POST handler that validates input, hashes the password with werkzeug, inserts a new row into the `users` table, and signs the user in via `flask.session`. After successful registration, the user lands on the profile page (which is still a stub at this stage — that's Step 4). Until then we redirect to `/login` with a flash message so the experience remains navigable.

This is the first feature that exercises the data layer in production, so it also establishes session handling (Flask `SECRET_KEY`, `flask.session`, `flask.flash`) and the project's password-hashing convention, both of which Login (Step 3) and every authenticated page will reuse.

## Depends on
- **Step 1 — Database setup** — `users` table must exist, `get_db()` must be importable from `database/db.py`. ✅ already complete on `main`.

## Routes
- `POST /register` — validates `name` / `email` / `password`, hashes the password, inserts a new user, starts a session, redirects to `/profile`. **Public.**
- `GET /register` — already exists; will be left as-is (renders `register.html`).

No other new routes. `/profile` is still the Step 4 stub for this step.

## Database changes
No database changes. The `users` table created in Step 1 already has every column we need:
`id`, `name`, `email` (UNIQUE), `password_hash`, `created_at`.

## Templates
- **Modify:** `templates/register.html`
    - Render flash messages from the category `error` at the top of the auth card (replacing or complementing the current `{% if error %}` block).
    - Render flash messages from the category `success` (e.g. "Account created — please sign in") after a redirect.
    - Keep the existing form (action, fields, classes) unchanged.
- **Create:** none. The success landing uses the existing `/login` page.

## Files to change
- `app.py` — add `POST` handling to the existing `register()` view, set `app.secret_key`, import `flash`, `redirect`, `request`, `session`, and `generate_password_hash` / `check_password_hash` from `werkzeug.security`, add a `create_user()` helper in `database/db.py` (or a thin wrapper in `app.py` — see Rules).
- `database/db.py` — add a single new helper: `create_user(conn, name, email, password) -> int` that inserts a row and returns the new `id`. (Keeps all SQL out of route functions, per CLAUDE.md.)
- `templates/register.html` — render flashed messages.

## Files to create
None.

## New dependencies
No new dependencies. Everything used (`flask.session`, `flask.flash`, `werkzeug.security.generate_password_hash`) is already pulled in by Flask + werkzeug 3.1.6 (already in `requirements.txt`).

## Rules for implementation
- **No SQLAlchemy, no ORM.** Use raw `sqlite3` via `database/db.py`'s `get_db()`.
- **No new pip packages.**
- **Parameterised queries only** — `?` placeholders, never f-strings in SQL.
- **All DB logic in `database/db.py`** — the route function may not contain raw SQL. Add a `create_user(conn, name, email, password) -> int` helper and call it from the route.
- **Passwords hashed with `werkzeug.security.generate_password_hash`.** Never store plaintext.
- **Email validation:** trim whitespace, lowercase the email, require `@` and a `.` in the domain (a regex is fine; or use `email-validator` — *no, not allowed, use stdlib only*). Also reject emails that already exist; let SQLite's `UNIQUE` constraint be the final guard and translate the resulting `IntegrityError` into a friendly "Email already registered" message.
- **Password validation:** minimum 8 characters; do not impose a max length but reject empty/whitespace-only. Do not echo the password back in any error message.
- **Name validation:** trim whitespace, non-empty, max 80 characters.
- **Session:** set `app.secret_key` from an env var `SECRET_KEY` if set, otherwise a development-only default with a clear comment that it must be changed for production. On successful registration, store `session["user_id"]` and `session["user_name"]`, then `flash("Account created — welcome to Spendly!", "success")` and `redirect(url_for("profile"))`.
- **Flash messaging:** use `flash(message, category)` and render via `get_flashed_messages(with_categories=True)` in the template so the success path (after redirect) can also display messages.
- **CSRF:** not required for this single-form step (out of scope), but document that a follow-up will add it.
- **CSS:** any new styles must use the existing CSS variables in `static/css/style.css` (`--danger`, `--danger-light`, `--accent`, etc.). Never hardcode hex values.
- **Templates:** `register.html` must keep `{% extends "base.html" %}` and use `url_for()` for the form action and any internal links.
- **Error handling:** on `sqlite3.IntegrityError` (duplicate email), re-render the form with the friendly error. On any other DB error, log and `abort(500)`. Use `flask.abort`, never bare `return "error string"` (per CLAUDE.md).
- **Idempotency:** the GET handler stays unchanged; do not pre-create any user from a GET.

## Definition of done
- [ ] `app.secret_key` is configured (env var with dev fallback + comment).
- [ ] `POST /register` with valid `name`, `email`, `password` (≥ 8 chars) creates a row in `users` whose `password_hash` is a werkzeug hash (starts with `scrypt:` or `pbkdf2:`), sets `session["user_id"]` and `session["user_name"]`, flashes a success message, and `302`-redirects to `/profile`.
- [ ] `POST /register` with a missing field, an invalid email, a password under 8 characters, or an empty name re-renders `register.html` with a user-facing error message and HTTP status `200` (form resubmission should still work).
- [ ] `POST /register` with an email that already exists in `users` re-renders the form with the message "Email already registered" — no second row is created, no unhandled `IntegrityError` is raised.
- [ ] `GET /register` still renders `register.html` with HTTP `200` and behaves exactly as before for an unauthenticated visitor.
- [ ] The flashed success message is visible on the page the user lands on (currently `/profile` stub is fine; once Step 4 lands, the profile page renders it).
- [ ] No raw SQL appears in `app.py`; the new insert is in `database/db.py`.
- [ ] No new pip packages added; `requirements.txt` is unchanged.
- [ ] No new hardcoded hex values in any CSS — only existing variables from `static/css/style.css` (or new variables added there).
- [ ] Visiting `/register` after logging in still works (does not 500) — though a logged-in redirect-to-profile polish can wait for Step 4.
- [ ] App starts without errors on `python app.py` and remains on port 5001.
