"""Authentication routes for Craft World Tools.

This module is ready to be wired into app.py with:

    from craftworld_tools.routes.auth import register_auth_routes
    register_auth_routes(app, BASE_TEMPLATE, has_uid_flag)

The old inline routes in app.py should be removed at the same time to avoid
registering duplicate /login, /register, and /logout URLs.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import redirect, render_template_string, request, session, url_for

from craftworld_tools.services.users import authenticate_user, create_user


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


def _login_user(user: dict[str, Any]) -> None:
    session["user_id"] = int(user["id"])
    session["username"] = user["username"]


def register_auth_routes(
    app: Any,
    base_template: str,
    has_uid_flag: HasUidFlag,
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
                try:
                    user = create_user(username, password)
                    _login_user(user)
                    return redirect(url_for("boosts"))
                except ValueError as exc:
                    error = str(exc)

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
                user = authenticate_user(username, password)
                if user is None:
                    error = "Invalid username or password."
                else:
                    _login_user(user)
                    return redirect(url_for("boosts"))

        return _render_page(base_template, LOGIN_TEMPLATE, error=error, has_uid_flag=has_uid_flag)

    @app.route("/logout")
    def logout():
        session.pop("user_id", None)
        session.pop("username", None)
        return redirect(url_for("index"))
