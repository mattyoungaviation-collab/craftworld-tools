"""Authentication routes for Craft World Tools.

This module is ready to be wired into app.py with:

    from craftworld_tools.routes.auth import register_auth_routes
    register_auth_routes(app, BASE_TEMPLATE, has_uid_flag, get_db_connection)

The old inline routes in app.py should be removed at the same time to avoid
registering duplicate /login, /register, and /logout URLs.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


GetDbConnection = Callable[[], Any]
HasUidFlag = Callable[[], bool]


REGISTER_TEMPLATE = """
# Create Account

Create a login so your Mastery & Workshop boosts are saved to your account,
independent of which Account ID you're looking at.

<form method="post" class="card">
  <label>Username</label>
  <input name="username" autocomplete="username" required>
  <p class="muted">This is just for this site. It does not need to match your in-game name.</p>

  <label>Password</label>
  <input name="password" type="password" autocomplete="new-password" required>

  <label>Confirm password</label>
  <input name="confirm" type="password" autocomplete="new-password" required>

  <button type="submit">Create account</button>
</form>

<p>Already have an account? <a href="{{ url_for('login') }}">Log in</a>.</p>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}
"""


LOGIN_TEMPLATE = """
# Log In

Log into your account so your Mastery & Workshop boosts follow you, even while
you swap Account IDs to spy on other accounts.

<form method="post" class="card">
  <label>Username</label>
  <input name="username" autocomplete="username" required>

  <label>Password</label>
  <input name="password" type="password" autocomplete="current-password" required>

  <button type="submit">Log in</button>
</form>

<p>Need an account? <a href="{{ url_for('register') }}">Create one</a>.</p>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}
"""


def _render_page(base_template: str, content_template: str, *, error: Optional[str], has_uid_flag: HasUidFlag) -> str:
    inner = render_template_string(content_template, error=error)
    return render_template_string(
        base_template,
        content=inner,
        active_page="login",
        has_uid=has_uid_flag(),
    )


def register_auth_routes(
    app: Any,
    base_template: str,
    has_uid_flag: HasUidFlag,
    get_db_connection: GetDbConnection,
) -> None:
    """Register login/register/logout routes on the provided Flask app."""

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error: Optional[str] = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = (request.form.get("password") or "").strip()
            confirm = (request.form.get("confirm") or "").strip()

            if not username or not password:
                error = "Username and password are required."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                conn = get_db_connection()
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
                    existing = cur.fetchone()
                    if existing:
                        error = "That username is already taken."
                    else:
                        pwd_hash = generate_password_hash(password)
                        cur.execute(
                            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                            (username, pwd_hash),
                        )
                        conn.commit()
                        user_id = cur.lastrowid
                        session["user_id"] = user_id
                        session["username"] = username
                        return redirect(url_for("boosts"))
                finally:
                    conn.close()

        return _render_page(base_template, REGISTER_TEMPLATE, error=error, has_uid_flag=has_uid_flag)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error: Optional[str] = None
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = (request.form.get("password") or "").strip()

            if not username or not password:
                error = "Username and password are required."
            else:
                conn = get_db_connection()
                try:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id, password_hash FROM users WHERE username = ?",
                        (username,),
                    )
                    row = cur.fetchone()
                    if not row:
                        error = "Invalid username or password."
                    else:
                        user_id = row["id"]
                        pwd_hash = row["password_hash"]
                        if not check_password_hash(pwd_hash, password):
                            error = "Invalid username or password."
                        else:
                            session["user_id"] = user_id
                            session["username"] = username
                            return redirect(url_for("boosts"))
                finally:
                    conn.close()

        return _render_page(base_template, LOGIN_TEMPLATE, error=error, has_uid_flag=has_uid_flag)

    @app.route("/logout")
    def logout():
        session.pop("user_id", None)
        session.pop("username", None)
        return redirect(url_for("index"))
