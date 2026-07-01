"""Tests for Step 6 — date filter for the profile page.

These tests are derived from `.claude/specs/06-date-filter-profile.md` and
describe the contract that `GET /profile?date_from=...&date_to=...` must
satisfy. Each test asserts on a single, named behavior from the spec.
"""

import sqlite3
from datetime import date

import pytest
from app import app as flask_app

# Local helpers ------------------------------------------------------------


def _login_and_get_session_user_id(client) -> int:
    """Register + sign in `client`, then return the seeded user_id from the DB."""
    client.post(
        "/register",
        data={
            "name": "Test User",
            "email": "test@spendly.com",
            "password": "testpass123",
        },
    )
    conn = sqlite3.connect(flask_app.config["DATABASE"])
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("test@spendly.com",)
        ).fetchone()
        assert row is not None, "Expected a user row after registration"
        return row["id"]
    finally:
        conn.close()


def _insert_expense(user_id: int, amount: float, category: str, day: str) -> None:
    """Insert one expense row for `user_id` on ISO date `day`."""
    conn = sqlite3.connect(flask_app.config["DATABASE"])
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, day, f"{category} on {day}"),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. No-op baseline — GET /profile with no query params is the unfiltered view
# ---------------------------------------------------------------------------


def test_profile_with_no_query_params_renders_unfiltered(auth_client):
    response = auth_client.get("/profile")
    assert response.status_code == 200
    assert b"profile-filter-bar" in response.data
    # The unfiltered view must not highlight any preset as active.
    assert b"profile-preset--active" not in response.data


# ---------------------------------------------------------------------------
# 2. date_from + date_to filter all three sections (summary, transactions, breakdown)
# ---------------------------------------------------------------------------


def test_profile_with_valid_date_range_filters_all_three_sections(auth_client):
    user_id = _login_and_get_session_user_id(auth_client)
    # Two expenses inside the window, one outside.
    _insert_expense(user_id, 100.0, "Food", "2026-03-05")
    _insert_expense(user_id, 200.0, "Food", "2026-04-15")
    _insert_expense(user_id, 999.0, "Food", "2026-05-20")  # outside

    response = auth_client.get(
        "/profile?date_from=2026-03-01&date_to=2026-04-30"
    )
    assert response.status_code == 200

    body = response.data
    # The row inside the window must appear in the transactions list.
    assert b"2026-03-05" in body
    assert b"2026-04-15" in body
    # The row outside the window must NOT appear.
    assert b"2026-05-20" not in body

    # Summary must reflect the filtered total (100 + 200 = 300), not 1299.
    assert b"\xe2\x82\xb9300.00" in body


# ---------------------------------------------------------------------------
# 3. Preset buttons render and resolve to the correct query params
# ---------------------------------------------------------------------------


def test_preset_links_render_with_expected_query_params(auth_client):
    today = date.today()
    # Compute the expected bounds the same way the implementation does.
    expected = {
        "All Time": ("", ""),
        "This Month": (today.strftime("%Y-%m") + "-01", today.isoformat()),
        "Last 3 Months": _month_first(today, 2),  # set below
        "Last 6 Months": _month_first(today, 5),  # set below
    }
    # Fill in the multi-month presets using the same calendar math.
    expected["Last 3 Months"] = (
        _shift_months(today, -2).strftime("%Y-%m") + "-01",
        today.isoformat(),
    )
    expected["Last 6 Months"] = (
        _shift_months(today, -5).strftime("%Y-%m") + "-01",
        today.isoformat(),
    )

    response = auth_client.get("/profile")
    assert response.status_code == 200
    body = response.data.decode()

    for name, (df, dt) in expected.items():
        if df and dt:
            expected_href = f"/profile?date_from={df}&date_to={dt}"
        else:
            # "All Time" must produce a clean /profile URL (no query params).
            expected_href = "/profile"
        # The rendered preset anchor must point to that URL.
        assert expected_href in body, f"Missing preset link for {name}: {expected_href}"


def test_preset_links_match_url_for_helper(auth_client):
    """Sanity check: url_for('profile', date_from=..., date_to=...) equals the
    rendered href for each preset, including the (None, None) 'All Time' case.
    """
    with flask_app.test_request_context():
        today = date.today()
        expected_pairs = {
            "All Time": (None, None),
            "This Month": (today.strftime("%Y-%m") + "-01", today.isoformat()),
            "Last 3 Months": (
                _shift_months(today, -2).strftime("%Y-%m") + "-01",
                today.isoformat(),
            ),
            "Last 6 Months": (
                _shift_months(today, -5).strftime("%Y-%m") + "-01",
                today.isoformat(),
            ),
        }
        for name, (df, dt) in expected_pairs.items():
            url = _profile_url(df, dt)
            response = auth_client.get(url)
            assert response.status_code == 200, name
            assert url.encode() in response.data, name


# ---------------------------------------------------------------------------
# 4. Malformed date strings fall back to the unfiltered view (no crash)
# ---------------------------------------------------------------------------


def test_profile_with_malformed_date_from_does_not_crash(auth_client):
    response = auth_client.get("/profile?date_from=not-a-date")
    assert response.status_code == 200
    assert b"profile-filter-bar" in response.data
    assert b"profile-preset--active" not in response.data  # no preset matched


def test_profile_with_malformed_date_to_does_not_crash(auth_client):
    response = auth_client.get("/profile?date_to=garbage")
    assert response.status_code == 200
    assert b"profile-filter-bar" in response.data
    assert b"profile-preset--active" not in response.data


def test_profile_with_both_bounds_malformed_does_not_crash(auth_client):
    response = auth_client.get("/profile?date_from=foo&date_to=bar")
    assert response.status_code == 200
    assert b"profile-filter-bar" in response.data


def test_profile_with_only_one_bound_supplied_does_not_crash(auth_client):
    # Per spec: a one-sided filter is ignored, route falls back to unfiltered.
    user_id = _login_and_get_session_user_id(auth_client)
    _insert_expense(user_id, 50.0, "Food", "2026-01-01")

    response_from_only = auth_client.get("/profile?date_from=2026-01-01")
    assert response_from_only.status_code == 200
    # Unfiltered view still shows the expense (no range applied).
    assert b"2026-01-01" in response_from_only.data

    response_to_only = auth_client.get("/profile?date_to=2026-01-01")
    assert response_to_only.status_code == 200
    assert b"2026-01-01" in response_to_only.data


# ---------------------------------------------------------------------------
# 5. Inverted range flashes the error and falls back to unfiltered
# ---------------------------------------------------------------------------


def test_profile_with_inverted_range_flashes_error_and_falls_back(auth_client):
    user_id = _login_and_get_session_user_id(auth_client)
    _insert_expense(user_id, 500.0, "Food", "2026-05-01")

    response = auth_client.get("/profile?date_from=2026-12-01&date_to=2026-01-01")
    assert response.status_code == 200

    # The exact error string from the spec must appear in the flashed messages.
    assert b"Start date must be before end date." in response.data

    # Fallback must be unfiltered, so the May expense is still visible.
    assert b"2026-05-01" in response.data
    # No preset should be highlighted as active after the fallback.
    assert b"profile-preset--active" not in response.data


# ---------------------------------------------------------------------------
# 6. Empty range shows zero totals and the empty states
# ---------------------------------------------------------------------------


def test_profile_with_empty_range_shows_zero_totals_and_empty_states(auth_client):
    user_id = _login_and_get_session_user_id(auth_client)
    _insert_expense(user_id, 999.0, "Food", "2025-01-15")  # far outside

    response = auth_client.get("/profile?date_from=2030-01-01&date_to=2030-01-31")
    assert response.status_code == 200
    body = response.data

    # Summary totals must reflect zero in the filtered range.
    assert b"0 expenses" in body or b">0<" in body or b"profile-empty" in body
    # ₹0.00 must appear at least once.
    assert b"\xe2\x82\xb90.00" in body
    # Empty state copy for transactions and breakdown must render.
    assert b"No transactions in this range" in body
    assert b"No categories in this range" in body


# ---------------------------------------------------------------------------
# 7. Active preset is visually highlighted (profile-preset--active)
# ---------------------------------------------------------------------------


def test_active_preset_is_highlighted_with_active_class(auth_client):
    today = date.today()
    # Build the "This Month" preset bounds exactly like the route does.
    this_month_from = today.strftime("%Y-%m") + "-01"
    this_month_to = today.isoformat()

    response = auth_client.get(
        f"/profile?date_from={this_month_from}&date_to={this_month_to}"
    )
    assert response.status_code == 200
    body = response.data.decode()

    # The "This Month" anchor must carry the active class.
    assert (
        f'class="profile-preset profile-preset--active" href="/profile?'
        f'date_from={this_month_from}&date_to={this_month_to}">This Month'
        in body
    )


def test_all_time_preset_is_highlighted_when_no_filter_applied(auth_client):
    response = auth_client.get("/profile")
    assert response.status_code == 200
    body = response.data.decode()
    # The "All Time" anchor must carry the active class on the unfiltered view.
    assert (
        'class="profile-preset profile-preset--active" href="/profile">All Time'
        in body
    )


# ---------------------------------------------------------------------------
# 8. User with no expenses sees empty states across all three sections
# ---------------------------------------------------------------------------


def test_user_with_no_expenses_sees_empty_states(auth_client):
    # A freshly-registered user owns no expenses.
    response = auth_client.get("/profile")
    assert response.status_code == 200
    body = response.data

    # All three empty states must render (summary + transactions + breakdown).
    assert b"No expenses in this range" in body
    assert b"No transactions in this range" in body
    assert b"No categories in this range" in body
    # ₹0.00 must appear in the summary.
    assert b"\xe2\x82\xb90.00" in body


def test_user_with_no_expenses_filtered_also_sees_empty_states(auth_client):
    response = auth_client.get("/profile?date_from=2026-01-01&date_to=2026-12-31")
    assert response.status_code == 200
    body = response.data
    assert b"No expenses in this range" in body
    assert b"No transactions in this range" in body
    assert b"No categories in this range" in body


# ---------------------------------------------------------------------------
# 9. Auth guard — signed-out requests redirect to /login with a flash
# ---------------------------------------------------------------------------


def test_profile_when_signed_out_redirects_to_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_when_signed_out_flashes_sign_in_message(client):
    # Follow the redirect to see the flashed message on the destination page.
    response = client.get("/profile", follow_redirects=True)
    assert response.status_code == 200
    assert b"Please sign in to view your profile." in response.data


# ---------------------------------------------------------------------------
# 10. The ₹ symbol is rendered for summary, transactions, and breakdown amounts
# ---------------------------------------------------------------------------


def test_rupee_symbol_appears_in_summary_transactions_and_breakdown(auth_client):
    user_id = _login_and_get_session_user_id(auth_client)
    _insert_expense(user_id, 250.0, "Food", "2026-04-01")
    _insert_expense(user_id, 750.0, "Transport", "2026-04-02")

    response = auth_client.get("/profile?date_from=2026-04-01&date_to=2026-04-30")
    assert response.status_code == 200
    body = response.data
    rupee = b"\xe2\x82\xb9"  # UTF-8 bytes for ₹

    # The summary, transactions, and breakdown all format amounts with ₹.
    # We expect the symbol to appear at least three times: once per section.
    assert body.count(rupee) >= 3


# ---------------------------------------------------------------------------
# Edge cases — inclusive bounds on both ends
# ---------------------------------------------------------------------------


def test_date_to_equal_to_row_date_is_inclusive(auth_client):
    user_id = _login_and_get_session_user_id(auth_client)
    _insert_expense(user_id, 75.0, "Food", "2026-02-10")

    response = auth_client.get("/profile?date_from=2026-02-01&date_to=2026-02-10")
    assert response.status_code == 200
    assert b"2026-02-10" in response.data
    assert b"\xe2\x82\xb975.00" in response.data


def test_date_from_equal_to_row_date_is_inclusive(auth_client):
    user_id = _login_and_get_session_user_id(auth_client)
    _insert_expense(user_id, 88.0, "Food", "2026-02-20")

    response = auth_client.get("/profile?date_from=2026-02-20&date_to=2026-02-28")
    assert response.status_code == 200
    assert b"2026-02-20" in response.data
    assert b"\xe2\x82\xb988.00" in response.data


# ---------------------------------------------------------------------------
# Small helpers used by the preset URL tests
# ---------------------------------------------------------------------------


def _shift_months(d: date, delta: int) -> date:
    """Return `d` shifted by `delta` calendar months (no day overflow handling)."""
    year = d.year
    month = d.month + delta
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return date(year, month, d.day)


def _month_first(d: date, months_back: int) -> tuple[str, str]:
    """(from, to) pair for a `months_back`-month window ending on `d`."""
    return (
        _shift_months(d.replace(day=1), -months_back).isoformat(),
        d.isoformat(),
    )


def _profile_url(date_from, date_to) -> str:
    """Mirror of url_for('profile', date_from=..., date_to=...) for assertions."""
    from flask import url_for

    return url_for("profile", date_from=date_from, date_to=date_to)