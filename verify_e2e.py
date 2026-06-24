"""End-to-end verification matrix for Spendly registration (Step 2).

Runs every check in sequence against the dev server at http://127.0.0.1:5001
and the local SQLite DB. Prints PASS/FAIL with evidence for each item.
"""

import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = "http://127.0.0.1:5001"
DB_PATH = os.path.join(
    r"C:\Users\satya\OneDrive\Desktop\Practice\Claude\expense-tracker",
    "spendly.db",
)


def open_session():
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener, cj


def cookie_names_from_opener(opener):
    """Return the cookie names held by the session opener, if any."""
    for h in opener.handlers:
        if hasattr(h, "cookiejar"):
            return [c.name for c in h.cookiejar]
    return []


def cookie_value(opener, name):
    for h in opener.handlers:
        if hasattr(h, "cookiejar"):
            for c in h.cookiejar:
                if c.name == name:
                    return c.value
    return None


def http(opener, method, path, data=None, headers=None, allow_redirect=True):
    url = BASE + path
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    else:
        req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        resp = opener.open(req)
        status = resp.status
        body_bytes = resp.read()
        final_url = resp.geturl()
        hdrs_out = dict(resp.getheaders())
    except urllib.error.HTTPError as e:
        status = e.code
        body_bytes = e.read()
        final_url = url
        hdrs_out = dict(e.headers.items())
    return status, body_bytes.decode("utf-8", errors="replace"), final_url, hdrs_out


def db_count_users():
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def db_row_for_email(email):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT id, name, email, password_hash, created_at FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()


# --------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------- #
print("=" * 70)
print("SPENDLY REGISTRATION — END-TO-END VERIFICATION")
print("=" * 70)

stamp = str(int(time.time()))
NEW_EMAIL = f"test_{stamp}@example.com"
results = []


def record(name, ok, evidence):
    results.append((name, ok, evidence))
    status = "PASS" if ok else "FAIL"
    print(f"\n[{status}] {name}")
    for line in evidence:
        print(f"        {line}")


# --------------------------------------------------------------------- #
# Test 2: GET /register renders 200 with form
# --------------------------------------------------------------------- #
opener, _ = open_session()
status, body, url, _ = http(opener, "GET", "/register")
form_ok = (
    status == 200
    and 'action="/register"' in body
    and 'name="name"' in body
    and 'name="email"' in body
    and 'name="password"' in body
    and "auth-error" not in body
)
record(
    "2. GET /register renders 200 with form",
    form_ok,
    [
        f"status: {status}",
        f"action=/register present: {'action=\"/register\"' in body}",
        f"name input present: {'name=\"name\"' in body}",
        f"email input present: {'name=\"email\"' in body}",
        f"password input present: {'name=\"password\"' in body}",
        f"no auth-error rendered: {'auth-error' not in body}",
    ],
)

# --------------------------------------------------------------------- #
# Test 3: POST /register with valid input
# --------------------------------------------------------------------- #
before_count = db_count_users()
status, body, url, hdrs = http(
    opener,
    "POST",
    "/register",
    data={"name": "Test User", "email": NEW_EMAIL, "password": "password123"},
    allow_redirect=False,
)
location = hdrs.get("Location") or hdrs.get("location") or ""
set_cookie = hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or ""
row = db_row_for_email(NEW_EMAIL)
hash_prefix = (row["password_hash"][:7] if row else "")
hash_ok = hash_prefix in ("scrypt:", "pbkdf2:")
new_count = db_count_users()

# follow the redirect manually with the same opener so cookies stick
status2, body2, url2, hdrs2 = http(opener, "GET", "/profile")

cookie_names = cookie_names_from_opener(opener)
session_cookie_present = "session" in cookie_names

record(
    "3. POST /register with valid input",
    (
        status == 302
        and location == "/profile"
        and bool(set_cookie)
        and hash_ok
        and session_cookie_present
        and new_count == before_count + 1
    ),
    [
        f"status: {status}",
        f"Location: {location}",
        f"Set-Cookie header present: {bool(set_cookie)}",
        f"cookie jar names: {cookie_names}",
        f"new row id={row['id'] if row else 'MISSING'} name={row['name'] if row else 'MISSING'}",
        f"password_hash starts with: '{hash_prefix}' (scrypt:/pbkdf2: required)",
        f"user count: {before_count} -> {new_count}",
        f"GET /profile after redirect status: {status2} body: {body2[:80]!r}",
    ],
)

# --------------------------------------------------------------------- #
# Test 4: POST /register with password="short"
# --------------------------------------------------------------------- #
before_count = db_count_users()
status, body, url, _ = http(
    opener,
    "POST",
    "/register",
    data={"name": "Short Pw", "email": f"short_{stamp}@example.com", "password": "short"},
)
after_count = db_count_users()
# Expect the error text inside an auth-error div
has_msg = (
    "Password must be at least 8 characters." in body
    and re.search(
        r'<div class="auth-error">[^<]*Password must be at least 8 characters\.',
        body,
    )
    is not None
)
record(
    "4. POST /register with password='short'",
    status == 200 and has_msg and before_count == after_count,
    [
        f"status: {status}",
        f"message inside auth-error: {has_msg}",
        f"user count: {before_count} -> {after_count}",
    ],
)

# --------------------------------------------------------------------- #
# Test 5: POST /register with email="not-an-email"
# --------------------------------------------------------------------- #
before_count = db_count_users()
status, body, url, _ = http(
    opener,
    "POST",
    "/register",
    data={"name": "Bad Email", "email": "not-an-email", "password": "password123"},
)
after_count = db_count_users()
has_msg = (
    "Please enter a valid email address." in body
    and re.search(
        r'<div class="auth-error">[^<]*Please enter a valid email address\.',
        body,
    )
    is not None
)
record(
    "5. POST /register with email='not-an-email'",
    status == 200 and has_msg and before_count == after_count,
    [
        f"status: {status}",
        f"message inside auth-error: {has_msg}",
        f"user count: {before_count} -> {after_count}",
    ],
)

# --------------------------------------------------------------------- #
# Test 6: POST /register with name="   " (whitespace only)
# --------------------------------------------------------------------- #
before_count = db_count_users()
status, body, url, _ = http(
    opener,
    "POST",
    "/register",
    data={"name": "   ", "email": f"blankname_{stamp}@example.com", "password": "password123"},
)
after_count = db_count_users()
has_msg = (
    "Please enter your name" in body
    and re.search(
        r'<div class="auth-error">[^<]*Please enter your name',
        body,
    )
    is not None
)
record(
    "6. POST /register with name='   '",
    status == 200 and has_msg and before_count == after_count,
    [
        f"status: {status}",
        f"message inside auth-error: {has_msg}",
        f"user count: {before_count} -> {after_count}",
    ],
)

# --------------------------------------------------------------------- #
# Test 7: POST /register with same valid email as test #3
# --------------------------------------------------------------------- #
before_row = db_row_for_email(NEW_EMAIL)
before_count_for_email = 1 if before_row else 0
status, body, url, _ = http(
    opener,
    "POST",
    "/register",
    data={"name": "Test User Duplicate", "email": NEW_EMAIL, "password": "password123"},
)
after_row = db_row_for_email(NEW_EMAIL)
after_count_for_email = 1 if after_row else 0
has_msg = (
    "Email already registered" in body
    and re.search(
        r'<div class="auth-error">[^<]*Email already registered',
        body,
    )
    is not None
)
record(
    "7. POST /register with duplicate email",
    status == 200 and has_msg and after_count_for_email == 1 and before_count_for_email == 1,
    [
        f"status: {status}",
        f"message inside auth-error: {has_msg}",
        f"row count for email: {before_count_for_email} -> {after_count_for_email}",
    ],
)

# --------------------------------------------------------------------- #
# Test 8: GET /register after successful registration
# --------------------------------------------------------------------- #
status, body, url, _ = http(opener, "GET", "/register")
no_500 = status != 500 and "Internal Server Error" not in body
record(
    "8. GET /register after successful registration",
    status == 200 and no_500,
    [
        f"status: {status}",
        f"no 500 / Internal Server Error: {no_500}",
    ],
)

# --------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------- #
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
all_pass = True
for name, ok, _ in results:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}")
    if not ok:
        all_pass = False
print()
print("OVERALL:", "PASS" if all_pass else "FAIL")
sys.exit(0 if all_pass else 1)
